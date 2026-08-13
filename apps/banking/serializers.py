from rest_framework import serializers

from .models import Account, LedgerEntry, Transfer


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
    to_account = serializers.UUIDField()
    amount_cents = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, data):
        if data["from_account"] == data["to_account"]:
            raise serializers.ValidationError("Cannot transfer to the same account.")
        return data


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = ["id", "from_account", "to_account", "amount_cents", "note", "status", "created_at"]
        read_only_fields = fields
