from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Account, AccountStatus, LedgerEntry, Transfer
from .serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    LedgerEntrySerializer,
    TransferCreateSerializer,
    TransferSerializer,
)
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

        return Response(TransferSerializer(transfer).data, status=status.HTTP_201_CREATED)
