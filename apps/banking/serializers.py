from rest_framework import serializers

from .models import Account, DepositRequest, LedgerEntry, ManualAdjustment, Transfer, WithdrawalRequest


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
