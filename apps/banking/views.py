import stripe
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.auditlog.utils import log_action
from apps.notifications.models import Notification
from apps.users.permissions import IsApprover

from .models import Account, AccountStatus, DepositRequest, LedgerEntry, ManualAdjustment, Transfer, WithdrawalRequest
from .serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    AdminWithdrawalSerializer,
    DepositCreateSerializer,
    DepositSerializer,
    LedgerEntrySerializer,
    ManualAdjustmentCreateSerializer,
    ManualAdjustmentSerializer,
    TransferCreateSerializer,
    TransferSerializer,
    WithdrawalCreateSerializer,
    WithdrawalSerializer,
)
from .stripe_service import create_deposit_intent, create_withdrawal_payout, verify_webhook_event
from .utils import generate_account_number


class AccountListCreateView(APIView):
    def get(self, request):
        accounts = Account.objects.filter(owner=request.user).order_by("-created_at")
        return Response(AccountSerializer(accounts, many=True).data)

    def post(self, request):
        serializer = AccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = Account.objects.create(
            owner=request.user,
            account_number=generate_account_number(),
            **serializer.validated_data,
        )
        return Response(AccountSerializer(account).data, status=status.HTTP_201_CREATED)


class AccountTransactionsView(APIView):
    def get(self, request, pk):
        # Filtering by owner in the same query as pk means a mismatched owner
        # 404s exactly like a nonexistent account, instead of leaking existence.
        account = get_object_or_404(Account, pk=pk, owner=request.user)
        entries = account.ledger_entries.order_by("-created_at")
        return Response(LedgerEntrySerializer(entries, many=True).data)


class TransferCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "transfer"

    def post(self, request):
        serializer = TransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.can_transact:
            return Response(
                {"error": "Verify your email and complete KYC before transferring funds."},
                status=status.HTTP_403_FORBIDDEN,
            )

        amount = data["amount_cents"]

        to_account_id = Account.objects.filter(
            account_number=data["to_account"]
        ).values_list("id", flat=True).first()
        if to_account_id is None:
            return Response({"error": "Destination account number not found."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            # Lock both rows for the duration of the transfer so a concurrent
            # transfer can't read a stale balance; ordering by id keeps two
            # transfers between the same pair of accounts from deadlocking.
            locked = Account.objects.select_for_update().filter(
                id__in=[data["from_account"], to_account_id]
            ).order_by("id")
            accounts_by_id = {a.id: a for a in locked}
            from_account = accounts_by_id.get(data["from_account"])
            to_account = accounts_by_id.get(to_account_id)

            if from_account is None or from_account.owner_id != request.user.id:
                return Response({"error": "Source account not found."}, status=status.HTTP_404_NOT_FOUND)
            if to_account is None:
                return Response({"error": "Destination account number not found."}, status=status.HTTP_404_NOT_FOUND)
            if from_account.id == to_account.id:
                return Response({"error": "Cannot transfer to the same account."}, status=status.HTTP_400_BAD_REQUEST)
            if from_account.status != AccountStatus.ACTIVE:
                return Response({"error": "Source account is not active."}, status=status.HTTP_400_BAD_REQUEST)
            if to_account.status != AccountStatus.ACTIVE:
                return Response({"error": "Destination account is not active."}, status=status.HTTP_400_BAD_REQUEST)
            if from_account.balance_cents() < amount:
                return Response({"error": "Insufficient funds."}, status=status.HTTP_400_BAD_REQUEST)

            transfer = Transfer.objects.create(
                from_account=from_account,
                to_account=to_account,
                amount_cents=amount,
                note=data.get("note", ""),
                status=Transfer.Status.POSTED,
            )
            LedgerEntry.objects.create(
                account=from_account,
                amount_cents=-amount,
                description=f"Transfer to {to_account.account_number}",
                status=LedgerEntry.Status.POSTED,
                source_type=LedgerEntry.SourceType.TRANSFER,
                source_id=transfer.id,
            )
            LedgerEntry.objects.create(
                account=to_account,
                amount_cents=amount,
                description=f"Transfer from {from_account.account_number}",
                status=LedgerEntry.Status.POSTED,
                source_type=LedgerEntry.SourceType.TRANSFER,
                source_id=transfer.id,
            )
            Notification.objects.create(
                user=from_account.owner,
                category=Notification.Category.TRANSACTION,
                title="Transfer sent",
                body=f"Sent from {from_account.name} to account •••• {to_account.account_number[-4:]}",
            )
            Notification.objects.create(
                user=to_account.owner,
                category=Notification.Category.TRANSACTION,
                title="Transfer received",
                body=f"Received into {to_account.name} from account •••• {from_account.account_number[-4:]}",
            )

        return Response(TransferSerializer(transfer).data, status=status.HTTP_201_CREATED)


class DepositListCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "deposit"

    def get(self, request):
        deposits = DepositRequest.objects.filter(account__owner=request.user).order_by("-created_at")
        return Response(DepositSerializer(deposits, many=True).data)

    def post(self, request):
        serializer = DepositCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.can_transact:
            return Response(
                {"error": "Verify your email and complete KYC before making a deposit."},
                status=status.HTTP_403_FORBIDDEN,
            )

        account = get_object_or_404(Account, pk=data["account"], owner=request.user)
        if account.status != AccountStatus.ACTIVE:
            return Response({"error": "Account is not active."}, status=status.HTTP_400_BAD_REQUEST)

        deposit = DepositRequest.objects.create(account=account, amount_cents=data["amount_cents"])

        try:
            intent = create_deposit_intent(
                amount_cents=data["amount_cents"],
                currency=account.currency,
                deposit_request_id=deposit.id,
                account_id=account.id,
            )
        except stripe.error.StripeError:
            deposit.status = DepositRequest.Status.FAILED
            deposit.save(update_fields=["status"])
            return Response(
                {"error": "Could not start the deposit. Try again."}, status=status.HTTP_502_BAD_GATEWAY
            )

        deposit.stripe_payment_intent_id = intent.id
        deposit.status = DepositRequest.Status.PROCESSING
        deposit.save(update_fields=["stripe_payment_intent_id", "status"])

        # client_secret is only returned here, never persisted — the frontend
        # uses it once with Stripe.js to collect card details and confirm.
        return Response(
            {**DepositSerializer(deposit).data, "client_secret": intent.client_secret},
            status=status.HTTP_201_CREATED,
        )


class WithdrawalListCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "withdrawal"

    def get(self, request):
        withdrawals = WithdrawalRequest.objects.filter(account__owner=request.user).order_by("-created_at")
        return Response(WithdrawalSerializer(withdrawals, many=True).data)

    def post(self, request):
        serializer = WithdrawalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        amount = data["amount_cents"]

        if not request.user.can_transact:
            return Response(
                {"error": "Verify your email and complete KYC before withdrawing funds."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            account = get_object_or_404(
                Account.objects.select_for_update(), pk=data["account"], owner=request.user
            )
            if account.status != AccountStatus.ACTIVE:
                return Response({"error": "Account is not active."}, status=status.HTTP_400_BAD_REQUEST)
            if account.available_cents() < amount:
                return Response({"error": "Insufficient available funds."}, status=status.HTTP_400_BAD_REQUEST)

            auto_approved = amount <= WithdrawalRequest.AUTO_APPROVE_LIMIT_CENTS
            withdrawal = WithdrawalRequest.objects.create(
                account=account,
                amount_cents=amount,
                destination_account_number=data["destination_account_number"],
                destination_routing_number=data["destination_routing_number"],
                status=WithdrawalRequest.Status.APPROVED if auto_approved else WithdrawalRequest.Status.PENDING,
            )

            # Hold the funds immediately so a concurrent withdrawal or
            # transfer can't spend the same balance while this one is in
            # flight or awaiting compliance review — the pending status
            # keeps it out of balance_cents() but visible via held_cents().
            LedgerEntry.objects.create(
                account=account,
                amount_cents=-amount,
                description=f"Withdrawal to {data['destination_account_number']}",
                status=LedgerEntry.Status.PENDING,
                source_type=LedgerEntry.SourceType.WITHDRAWAL,
                source_id=withdrawal.id,
            )

        if not auto_approved:
            return Response(WithdrawalSerializer(withdrawal).data, status=status.HTTP_201_CREATED)

        try:
            payout = create_withdrawal_payout(
                amount_cents=amount,
                currency=account.currency,
                withdrawal_request_id=withdrawal.id,
                account_id=account.id,
            )
        except stripe.error.StripeError:
            withdrawal.status = WithdrawalRequest.Status.FAILED
            withdrawal.save(update_fields=["status"])
            LedgerEntry.objects.filter(
                source_type=LedgerEntry.SourceType.WITHDRAWAL, source_id=withdrawal.id
            ).update(status=LedgerEntry.Status.FAILED)
            return Response(
                {"error": "Could not start the withdrawal. Try again."}, status=status.HTTP_502_BAD_GATEWAY
            )

        withdrawal.stripe_payout_id = payout.id
        withdrawal.status = WithdrawalRequest.Status.PROCESSING
        withdrawal.save(update_fields=["stripe_payout_id", "status"])

        return Response(WithdrawalSerializer(withdrawal).data, status=status.HTTP_201_CREATED)


class StripeWebhookView(APIView):
    """
    No JWT here — Stripe calls this, not a logged-in user. Authenticity
    comes entirely from the signature check against STRIPE_WEBHOOK_SECRET.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        try:
            event = verify_webhook_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""))
        except (ValueError, stripe.error.SignatureVerificationError):
            return Response({"error": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

        event_type = event["type"]
        obj = event["data"]["object"]

        if event_type == "payment_intent.succeeded":
            self._settle_deposit(obj["id"], DepositRequest.Status.SUCCEEDED)
        elif event_type == "payment_intent.payment_failed":
            self._settle_deposit(obj["id"], DepositRequest.Status.FAILED)
        elif event_type == "payout.paid":
            self._settle_withdrawal(obj["id"], succeeded=True)
        elif event_type == "payout.failed":
            self._settle_withdrawal(obj["id"], succeeded=False)
        # Other event types (e.g. payment_intent.created) are ignored.

        return Response({"received": True})

    @staticmethod
    def _settle_deposit(payment_intent_id, new_status):
        with transaction.atomic():
            deposit = (
                DepositRequest.objects.select_for_update()
                .filter(stripe_payment_intent_id=payment_intent_id)
                .exclude(status__in=[DepositRequest.Status.SUCCEEDED, DepositRequest.Status.FAILED])
                .first()
            )
            if not deposit:
                return  # already settled (Stripe retries webhooks) or an intent we didn't create

            deposit.status = new_status
            deposit.save(update_fields=["status"])

            if new_status == DepositRequest.Status.SUCCEEDED:
                LedgerEntry.objects.create(
                    account=deposit.account,
                    amount_cents=deposit.amount_cents,
                    description="Deposit via Stripe",
                    status=LedgerEntry.Status.POSTED,
                    source_type=LedgerEntry.SourceType.DEPOSIT,
                    source_id=deposit.id,
                    provider_ref=payment_intent_id,
                )
                Notification.objects.create(
                    user=deposit.account.owner,
                    category=Notification.Category.TRANSACTION,
                    title="Deposit completed",
                    body=f"Your deposit to {deposit.account.name} has settled.",
                )
            else:
                Notification.objects.create(
                    user=deposit.account.owner,
                    category=Notification.Category.TRANSACTION,
                    title="Deposit failed",
                    body=f"Your deposit to {deposit.account.name} could not be completed.",
                )

    @staticmethod
    def _settle_withdrawal(payout_id, succeeded):
        with transaction.atomic():
            withdrawal = (
                WithdrawalRequest.objects.select_for_update()
                .filter(stripe_payout_id=payout_id)
                .exclude(status__in=[WithdrawalRequest.Status.SUCCEEDED, WithdrawalRequest.Status.FAILED])
                .first()
            )
            if not withdrawal:
                return

            hold = LedgerEntry.objects.filter(
                source_type=LedgerEntry.SourceType.WITHDRAWAL,
                source_id=withdrawal.id,
                status=LedgerEntry.Status.PENDING,
            ).first()

            if succeeded:
                withdrawal.status = WithdrawalRequest.Status.SUCCEEDED
                if hold:
                    hold.status = LedgerEntry.Status.POSTED
                    hold.provider_ref = payout_id
                    hold.save(update_fields=["status", "provider_ref"])
                Notification.objects.create(
                    user=withdrawal.account.owner,
                    category=Notification.Category.TRANSACTION,
                    title="Withdrawal completed",
                    body=f"Your withdrawal from {withdrawal.account.name} has completed.",
                )
            else:
                withdrawal.status = WithdrawalRequest.Status.FAILED
                if hold:
                    hold.status = LedgerEntry.Status.FAILED
                    hold.save(update_fields=["status"])
                Notification.objects.create(
                    user=withdrawal.account.owner,
                    category=Notification.Category.TRANSACTION,
                    title="Withdrawal failed",
                    body=f"Your withdrawal from {withdrawal.account.name} could not be completed.",
                )

            withdrawal.save(update_fields=["status"])


class AdminAccountFreezeView(APIView):
    """Freezing an account blocks money movement — distinct from blocking
    a user's login, which is a separate action on the User model."""

    permission_classes = [IsApprover]

    def post(self, request, pk):
        account = get_object_or_404(Account, pk=pk)
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        account.status = AccountStatus.FROZEN
        account.save(update_fields=["status"])
        Notification.objects.create(
            user=account.owner,
            category=Notification.Category.SECURITY,
            title="Account frozen",
            body=f"{account.name} has been frozen: {reason}",
        )
        log_action(request, "account.freeze", "Account", account.id, reason=reason)
        return Response(AccountSerializer(account).data)


class AdminAccountUnfreezeView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        account = get_object_or_404(Account, pk=pk)
        account.status = AccountStatus.ACTIVE
        account.save(update_fields=["status"])
        log_action(request, "account.unfreeze", "Account", account.id)
        return Response(AccountSerializer(account).data)


class AdminAdjustmentListCreateView(APIView):
    """The 'Fund/Debit' flow — the only sanctioned way to move money by
    hand. Requests at or under ManualAdjustment.AUTO_APPROVE_LIMIT_CENTS
    post immediately; anything larger sits PENDING_APPROVAL for a second
    approver (never the same staff member who requested it)."""

    permission_classes = [IsApprover]

    def get(self, request):
        adjustments = ManualAdjustment.objects.select_related(
            "account", "account__owner", "requested_by", "approved_by"
        ).order_by("-created_at")[:200]
        return Response(ManualAdjustmentSerializer(adjustments, many=True).data)

    def post(self, request):
        serializer = ManualAdjustmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = get_object_or_404(Account, pk=data["account"])
        amount = data["amount_cents"]
        auto_approved = abs(amount) <= ManualAdjustment.AUTO_APPROVE_LIMIT_CENTS

        with transaction.atomic():
            adjustment = ManualAdjustment.objects.create(
                account=account,
                amount_cents=amount,
                reason=data["reason"],
                requested_by=request.user,
                approved_by=request.user if auto_approved else None,
                status=ManualAdjustment.Status.POSTED if auto_approved else ManualAdjustment.Status.PENDING_APPROVAL,
                resolved_at=timezone.now() if auto_approved else None,
            )
            if auto_approved:
                LedgerEntry.objects.create(
                    account=account,
                    amount_cents=amount,
                    description=f"Manual adjustment: {data['reason']}",
                    status=LedgerEntry.Status.POSTED,
                    source_type=LedgerEntry.SourceType.MANUAL_ADJUSTMENT,
                    source_id=adjustment.id,
                )
                Notification.objects.create(
                    user=account.owner,
                    category=Notification.Category.TRANSACTION,
                    title="Account adjustment posted",
                    body=f"{account.name} was adjusted: {data['reason']}",
                )
            log_action(
                request,
                "adjustment.request" if not auto_approved else "adjustment.auto_post",
                "Account",
                account.id,
                reason=data["reason"],
                metadata={"amount_cents": amount, "adjustment_id": str(adjustment.id)},
            )

        return Response(ManualAdjustmentSerializer(adjustment).data, status=status.HTTP_201_CREATED)


class AdminAdjustmentApproveView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        adjustment = get_object_or_404(ManualAdjustment, pk=pk)
        if adjustment.status != ManualAdjustment.Status.PENDING_APPROVAL:
            return Response({"error": "This adjustment is not pending approval."}, status=status.HTTP_400_BAD_REQUEST)
        if adjustment.requested_by_id == request.user.id:
            return Response({"error": "You cannot approve your own request."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            adjustment.status = ManualAdjustment.Status.POSTED
            adjustment.approved_by = request.user
            adjustment.resolved_at = timezone.now()
            adjustment.save(update_fields=["status", "approved_by", "resolved_at"])
            LedgerEntry.objects.create(
                account=adjustment.account,
                amount_cents=adjustment.amount_cents,
                description=f"Manual adjustment: {adjustment.reason}",
                status=LedgerEntry.Status.POSTED,
                source_type=LedgerEntry.SourceType.MANUAL_ADJUSTMENT,
                source_id=adjustment.id,
            )
            Notification.objects.create(
                user=adjustment.account.owner,
                category=Notification.Category.TRANSACTION,
                title="Account adjustment posted",
                body=f"{adjustment.account.name} was adjusted: {adjustment.reason}",
            )
            log_action(
                request, "adjustment.approve", "Account", adjustment.account_id,
                reason=adjustment.reason, metadata={"adjustment_id": str(adjustment.id)},
            )

        return Response(ManualAdjustmentSerializer(adjustment).data)


class AdminAdjustmentRejectView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        adjustment = get_object_or_404(ManualAdjustment, pk=pk)
        if adjustment.status != ManualAdjustment.Status.PENDING_APPROVAL:
            return Response({"error": "This adjustment is not pending approval."}, status=status.HTTP_400_BAD_REQUEST)
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        adjustment.status = ManualAdjustment.Status.REJECTED
        adjustment.approved_by = request.user
        adjustment.resolved_at = timezone.now()
        adjustment.save(update_fields=["status", "approved_by", "resolved_at"])
        # No rejection_reason field on this model — the audit log entry is
        # the durable record of why, matching AuditLog's stated purpose.
        log_action(
            request, "adjustment.reject", "Account", adjustment.account_id,
            reason=reason, metadata={"adjustment_id": str(adjustment.id)},
        )
        return Response(ManualAdjustmentSerializer(adjustment).data)


class AdminWithdrawalListView(APIView):
    """The withdrawal half of the Transactions authorize/decline queue —
    only ever shows amounts above WithdrawalRequest.AUTO_APPROVE_LIMIT_CENTS,
    since anything at or under that already auto-processed in Stage 4."""

    permission_classes = [IsApprover]

    def get(self, request):
        withdrawals = WithdrawalRequest.objects.filter(
            status=WithdrawalRequest.Status.PENDING
        ).select_related("account", "account__owner").order_by("created_at")
        return Response(AdminWithdrawalSerializer(withdrawals, many=True).data)


class AdminWithdrawalApproveView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        withdrawal = get_object_or_404(WithdrawalRequest, pk=pk, status=WithdrawalRequest.Status.PENDING)
        withdrawal.status = WithdrawalRequest.Status.APPROVED
        withdrawal.reviewed_by = request.user
        withdrawal.save(update_fields=["status", "reviewed_by"])

        try:
            payout = create_withdrawal_payout(
                amount_cents=withdrawal.amount_cents,
                currency=withdrawal.account.currency,
                withdrawal_request_id=withdrawal.id,
                account_id=withdrawal.account_id,
            )
        except stripe.error.StripeError:
            withdrawal.status = WithdrawalRequest.Status.FAILED
            withdrawal.save(update_fields=["status"])
            LedgerEntry.objects.filter(
                source_type=LedgerEntry.SourceType.WITHDRAWAL, source_id=withdrawal.id
            ).update(status=LedgerEntry.Status.FAILED)
            log_action(request, "withdrawal.approve_failed", "WithdrawalRequest", withdrawal.id)
            return Response(
                {"error": "Could not start the withdrawal payout."}, status=status.HTTP_502_BAD_GATEWAY
            )

        withdrawal.stripe_payout_id = payout.id
        withdrawal.status = WithdrawalRequest.Status.PROCESSING
        withdrawal.save(update_fields=["stripe_payout_id", "status"])
        log_action(
            request, "withdrawal.approve", "WithdrawalRequest", withdrawal.id,
            metadata={"amount_cents": withdrawal.amount_cents},
        )
        return Response(AdminWithdrawalSerializer(withdrawal).data)


class AdminWithdrawalRejectView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        withdrawal = get_object_or_404(WithdrawalRequest, pk=pk, status=WithdrawalRequest.Status.PENDING)
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            withdrawal.status = WithdrawalRequest.Status.REJECTED
            withdrawal.reviewed_by = request.user
            withdrawal.rejection_reason = reason
            withdrawal.save(update_fields=["status", "reviewed_by", "rejection_reason"])
            # Releases the hold: the pending debit no longer counts against
            # held_cents(), so the funds are available again.
            LedgerEntry.objects.filter(
                source_type=LedgerEntry.SourceType.WITHDRAWAL,
                source_id=withdrawal.id,
                status=LedgerEntry.Status.PENDING,
            ).update(status=LedgerEntry.Status.FAILED)
            Notification.objects.create(
                user=withdrawal.account.owner,
                category=Notification.Category.TRANSACTION,
                title="Withdrawal declined",
                body=reason,
            )
            log_action(request, "withdrawal.reject", "WithdrawalRequest", withdrawal.id, reason=reason)

        return Response(AdminWithdrawalSerializer(withdrawal).data)
