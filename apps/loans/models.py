import uuid
from django.conf import settings
from django.db import models


class LoanProduct(models.Model):
    """
    Admin-configurable loan terms (your 'configure interest rates and
    repayment terms' requirement). Applications reference the product
    active at the time they were approved, so changing rates later never
    rewrites an existing customer's terms.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    annual_interest_rate_bps = models.PositiveIntegerField(help_text="Basis points, e.g. 950 = 9.50%")
    min_amount_cents = models.BigIntegerField()
    max_amount_cents = models.BigIntegerField()
    min_term_months = models.PositiveSmallIntegerField()
    max_term_months = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.annual_interest_rate_bps / 100}%)"


class LoanApplication(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DISBURSED = "disbursed", "Disbursed"
        CLOSED = "closed", "Closed"          # fully repaid

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="loan_applications")
    product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT, related_name="applications")
    requested_amount_cents = models.BigIntegerField()
    term_months = models.PositiveSmallIntegerField()
    purpose = models.CharField(max_length=255, blank=True)
    monthly_income_cents = models.BigIntegerField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    rejection_reason = models.CharField(max_length=255, blank=True)

    # Locked in at approval time from the product's current rate.
    approved_interest_rate_bps = models.PositiveIntegerField(null=True, blank=True)
    disbursement_account = models.ForeignKey(
        "banking.Account", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["applicant", "status"])]


class LoanRepayment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        PAID = "paid", "Paid"
        LATE = "late", "Late"
        MISSED = "missed", "Missed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name="repayments")
    installment_number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount_due_cents = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["installment_number"]
