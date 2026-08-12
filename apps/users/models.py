import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    SUPPORT = "support", "Support agent"          # can view accounts, verify KYC, cannot move money
    COMPLIANCE = "compliance", "Compliance officer"  # can approve manual adjustments, loans
    ADMIN = "admin", "Administrator"               # full access, still audit-logged
    SUPERADMIN = "superadmin", "Super administrator"


class KYCStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Unverified"
    PENDING = "pending", "Pending review"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"


class User(AbstractUser):
    """
    Email is the login identifier. `username` from AbstractUser is kept
    internally (Django admin expects it) but is auto-generated from email.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    email_verified = models.BooleanField(default=False)
    kyc_status = models.CharField(max_length=20, choices=KYCStatus.choices, default=KYCStatus.UNVERIFIED)

    # 2FA (TOTP via django-otp). is_2fa_enabled gates whether login requires
    # a second factor; the actual TOTP device lives in django_otp's tables.
    is_2fa_enabled = models.BooleanField(default=False)

    # Account-level controls an admin/compliance officer can apply.
    is_frozen = models.BooleanField(default=False)
    frozen_reason = models.TextField(blank=True)

    date_of_birth = models.DateField(null=True, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, blank=True)  # ISO 3166-1 alpha-2

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        indexes = [models.Index(fields=["email"]), models.Index(fields=["role"])]

    def __str__(self):
        return self.email

    @property
    def can_transact(self):
        """Central gate every money-movement view should check."""
        return self.email_verified and self.kyc_status == KYCStatus.VERIFIED and not self.is_frozen


class EmailVerificationToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verification_tokens")
    token_hash = models.CharField(max_length=128)  # SHA-256 hex of the raw token; raw token is only ever emailed
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_tokens")
    token_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
