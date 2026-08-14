from .models import AuditLog


def log_action(request, action, target_type, target_id, reason="", metadata=None):
    # Same forwarded-IP handling as RequestAuditMiddleware._client_ip — kept
    # independent of the middleware since views have request in hand anyway
    # and shouldn't depend on middleware ordering to log correctly.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    AuditLog.objects.create(
        actor=request.user,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        reason=reason,
        metadata=metadata or {},
        ip_address=ip,
    )
