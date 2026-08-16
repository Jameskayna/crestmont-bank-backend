import uuid
from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        SECURITY = "security", "Security"          # new login, password changed
        TRANSACTION = "transaction", "Transaction"
        LOAN = "loan", "Loan"
        CARD = "card", "Card"
        KYC = "kyc", "KYC"
        SYSTEM = "system", "System"                 # admin-broadcast messages

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=150)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]


class Notice(models.Model):
    """Admin-authored announcement, shown as a banner on the customer
    dashboard while active. Distinct from Notification: a Notice is one
    broadcast row read by everyone, not a per-user inbox item."""

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        URGENT = "urgent", "Urgent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    message = models.TextField()
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
