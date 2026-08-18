from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Account, Card, DepositRequest, LedgerEntry, ManualAdjustment, Transfer, WithdrawalRequest


class AccountSerializer(serializers.ModelSerializer):
    balance_cents = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            "id", "account_number", "routing_number", "name", "type",
            "currency", "status", "balance_cents", "created_at",
        ]
        read_only_fields = fields

    def get_balance_cents(self, obj):
        return obj.balance_cents()


class AccountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["name", "type", "currency"]


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            "id", "amount_cents", "description", "status",
            "source_type", "source_id", "created_at", "transaction_date",
        ]
        read_only_fields = fields


class TransferCreateSerializer(serializers.Serializer):
    from_account = serializers.UUIDField()
    to_account = serializers.CharField(max_length=17)
    amount_cents = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class TransferConfirmSerializer(serializers.Serializer):
    transfer_intent_id = serializers.UUIDField()
    code = serializers.CharField(max_length=6)


class TransferResendSerializer(serializers.Serializer):
    transfer_intent_id = serializers.UUIDField()


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = ["id", "from_account", "to_account", "amount_cents", "note", "status", "created_at"]
        read_only_fields = fields


class DepositCreateSerializer(serializers.Serializer):
    account = serializers.UUIDField()
    amount_cents = serializers.IntegerField(min_value=100)  # $1 minimum


class DepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepositRequest
        fields = ["id", "account", "amount_cents", "status", "created_at", "updated_at"]
        read_only_fields = fields


class WithdrawalCreateSerializer(serializers.Serializer):
    account = serializers.UUIDField()
    amount_cents = serializers.IntegerField(min_value=100)  # $1 minimum
    destination_account_number = serializers.CharField(max_length=17)
    destination_routing_number = serializers.CharField(max_length=9)


class WithdrawalSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            "id", "account", "amount_cents", "destination_account_number",
            "destination_routing_number", "status", "rejection_reason", "created_at", "updated_at",
        ]
        read_only_fields = fields


class AdminWithdrawalSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_owner_email = serializers.CharField(source="account.owner.email", read_only=True)

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id", "account", "account_name", "account_owner_email", "amount_cents",
            "destination_account_number", "destination_routing_number",
            "status", "rejection_reason", "created_at", "updated_at",
        ]
        read_only_fields = fields


class CardRequestCreateSerializer(serializers.Serializer):
    account = serializers.UUIDField()
    brand = serializers.ChoiceField(choices=Card.Brand.choices)
    card_type = serializers.ChoiceField(choices=Card.CardType.choices, required=False, default=Card.CardType.DEBIT)


class CardSerializer(serializers.ModelSerializer):
    """Customer-facing: no block_reason (that's staff detail), and the
    masked number is the most detail this app ever has to show — real
    PANs are never stored, see Card.provider_card_id. masked_number and
    expiry_display are None until a request is approved and last4/expiry
    actually exist."""

    cardholder_name = serializers.SerializerMethodField()
    masked_number = serializers.SerializerMethodField()
    expiry_display = serializers.SerializerMethodField()
    brand_display = serializers.CharField(source="get_brand_display", read_only=True)

    class Meta:
        model = Card
        fields = [
            "id", "account", "masked_number", "brand", "brand_display", "card_type", "expiry_display",
            "status", "rejection_reason", "cardholder_name", "created_at",
        ]
        read_only_fields = fields

    def get_cardholder_name(self, obj):
        owner = obj.account.owner
        return owner.get_full_name() or owner.email

    def get_masked_number(self, obj):
        return f"•••• •••• •••• {obj.last4}" if obj.last4 else None

    def get_expiry_display(self, obj):
        if not obj.expiry_month:
            return None
        return f"{obj.expiry_month:02d}/{str(obj.expiry_year)[-2:]}"


class AdminCardSerializer(serializers.ModelSerializer):
    cardholder_name = serializers.SerializerMethodField()
    cardholder_email = serializers.CharField(source="account.owner.email", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    masked_number = serializers.SerializerMethodField()
    brand_display = serializers.CharField(source="get_brand_display", read_only=True)
    reviewed_by_email = serializers.CharField(source="reviewed_by.email", read_only=True, default=None)

    class Meta:
        model = Card
        fields = [
            "id", "account", "account_name", "cardholder_name", "cardholder_email",
            "masked_number", "last4", "brand", "brand_display", "card_type", "expiry_month", "expiry_year",
            "status", "block_reason", "rejection_reason", "reviewed_by_email", "created_at",
        ]
        read_only_fields = fields

    def get_cardholder_name(self, obj):
        owner = obj.account.owner
        return owner.get_full_name() or owner.email

    def get_masked_number(self, obj):
        return f"•••• •••• •••• {obj.last4}" if obj.last4 else None


class ManualAdjustmentCreateSerializer(serializers.Serializer):
    account = serializers.UUIDField()
    amount_cents = serializers.IntegerField()  # signed: positive = credit, negative = debit
    reason = serializers.CharField(max_length=255)
    # Null means "today" — only set when recording something that
    # happened earlier but was never captured (e.g. an unlogged wire).
    # The account-created_at floor is checked in the view, where the
    # account is already fetched.
    transaction_date = serializers.DateField(required=False, allow_null=True, default=None)

    def validate_amount_cents(self, value):
        if value == 0:
            raise serializers.ValidationError("Amount cannot be zero.")
        return value

    def validate_transaction_date(self, value):
        if value is None:
            return value
        today = timezone.localdate()
        if value > today:
            raise serializers.ValidationError("Transaction date cannot be in the future.")
        if value < today - timedelta(days=ManualAdjustment.MAX_BACKDATE_DAYS):
            raise serializers.ValidationError(
                f"Transaction date cannot be more than {ManualAdjustment.MAX_BACKDATE_DAYS} days in the past."
            )
        return value


class ManualAdjustmentSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_owner_email = serializers.CharField(source="account.owner.email", read_only=True)
    requested_by_email = serializers.CharField(source="requested_by.email", read_only=True)
    approved_by_email = serializers.CharField(source="approved_by.email", read_only=True, default=None)

    class Meta:
        model = ManualAdjustment
        fields = [
            "id", "account", "account_name", "account_owner_email", "amount_cents", "reason",
            "transaction_date", "requested_by_email", "approved_by_email", "status", "created_at", "resolved_at",
        ]
        read_only_fields = fields
