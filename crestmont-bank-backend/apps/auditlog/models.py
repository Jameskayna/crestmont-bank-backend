import uuid
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Immutable record of every sensitive action: manual balance adjustments,
    account freezes, KYC decisions, loan approvals, role changes, admin
    logins. This is what makes 'admin can credit/debit/freeze accounts'
    safe to have at all — nothing happens without a durable, queryable
    trail of who did it, when, and why.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_actions"
    )
    action = models.CharField(max_length=100)          # e.g. "account.freeze", "adjustment.approve"
    target_type = models.CharField(max_length=50)       # e.g. "User", "Account", "LoanApplication"
    target_id = models.CharField(max_length=64)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # e.g. {"old_status": "active", "new_status": "frozen"}
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]
