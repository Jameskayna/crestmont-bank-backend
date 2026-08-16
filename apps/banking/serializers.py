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
            "source_type", "source_id", "created_at",
        ]
        read_only_fields = fields


class TransferCreateSerializer(serializers.Serializer):
    from_account = serializers.UUIDField()
    to_account = serializers.CharField(max_length=17)
    amount_cents = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


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

    def validate_amount_cents(self, value):
        if value == 0:
            raise serializers.ValidationError("Amount cannot be zero.")
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
            "requested_by_email", "approved_by_email", "status", "created_at", "resolved_at",
        ]
        read_only_fields = fields
