import uuid
from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        SECURITY = "security", "Security"          # new login, password changed
        TRANSACTION = "transaction", "Transaction"
        LOAN = "loan", "Loan"
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
