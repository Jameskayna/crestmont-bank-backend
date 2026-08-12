import threading

_local = threading.local()


class RequestAuditMiddleware:
    """
    Stashes the current request's user and IP in thread-local storage so
    that model-layer code (e.g. a signal on ManualAdjustment.save) can
    write an AuditLog entry without every call site having to thread the
    request through manually. Views that perform sensitive actions should
    still write explicit, descriptive AuditLog entries themselves — this
    middleware is a safety net, not the primary logging mechanism.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.user = getattr(request, "user", None)
        _local.ip = self._client_ip(request)
        try:
            return self.get_response(request)
        finally:
            _local.user = None
            _local.ip = None

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def get_current_user():
    return getattr(_local, "user", None)


def get_current_ip():
    return getattr(_local, "ip", None)
