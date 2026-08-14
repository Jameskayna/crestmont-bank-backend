import stripe
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.notifications.models import Notification

from .models import Account, AccountStatus, DepositRequest, LedgerEntry, Transfer, WithdrawalRequest
from .serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    DepositCreateSerializer,
    DepositSerializer,
    LedgerEntrySerializer,
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

        with transaction.atomic():
            # Lock both rows for the duration of the transfer so a concurrent
            # transfer can't read a stale balance; ordering by id keeps two
            # transfers between the same pair of accounts from deadlocking.
            locked = Account.objects.select_for_update().filter(
                id__in=[data["from_account"], data["to_account"]]
            ).order_by("id")
            accounts_by_id = {a.id: a for a in locked}
            from_account = accounts_by_id.get(data["from_account"])
            to_account = accounts_by_id.get(data["to_account"])

            if from_account is None or from_account.owner_id != request.user.id:
                return Response({"error": "Source account not found."}, status=status.HTTP_404_NOT_FOUND)
            if to_account is None:
                return Response({"error": "Destination account not found."}, status=status.HTTP_404_NOT_FOUND)
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
