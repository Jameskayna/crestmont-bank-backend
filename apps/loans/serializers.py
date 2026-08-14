from rest_framework import serializers

from .models import LoanApplication, LoanProduct, LoanRepayment


class LoanProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanProduct
        fields = [
            "id", "name", "annual_interest_rate_bps",
            "min_amount_cents", "max_amount_cents",
            "min_term_months", "max_term_months",
        ]
        read_only_fields = fields


class LoanApplicationCreateSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    requested_amount_cents = serializers.IntegerField(min_value=1)
    term_months = serializers.IntegerField(min_value=1)
    purpose = serializers.CharField(required=False, allow_blank=True, max_length=255)
    monthly_income_cents = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class LoanRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanRepayment
        fields = ["id", "installment_number", "due_date", "amount_due_cents", "status", "paid_at"]
        read_only_fields = fields


class LoanApplicationSerializer(serializers.ModelSerializer):
    product = LoanProductSerializer(read_only=True)
    repayments = LoanRepaymentSerializer(many=True, read_only=True)

    class Meta:
        model = LoanApplication
        fields = [
            "id", "product", "requested_amount_cents", "term_months", "purpose",
            "monthly_income_cents", "status", "rejection_reason",
            "approved_interest_rate_bps", "created_at", "updated_at", "repayments",
        ]
        read_only_fields = fields
