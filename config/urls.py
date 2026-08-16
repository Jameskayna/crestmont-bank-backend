from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse


def health(request):
    return JsonResponse({"ok": True})


urlpatterns = [
    path("admin/", admin.site.urls),  # Django's built-in admin — separate from the custom staff console
    path("health", health),
    path("auth/", include("apps.users.urls")),
    path("", include("apps.banking.urls")),  # accounts + transfers
    path("kyc/", include("apps.kyc.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.loans.urls")),
    # Staff console (role-gated, not a separate login) — kept in dedicated
    # staff_urls modules per app since users/kyc are mounted under their
    # own prefixes ("auth/", "kyc/") that a bare "staff/..." path wouldn't fit.
    path("", include("apps.users.staff_urls")),
    path("", include("apps.banking.staff_urls")),
    path("", include("apps.kyc.staff_urls")),
    path("", include("apps.loans.staff_urls")),
    path("", include("apps.notifications.staff_urls")),
    path("", include("apps.auditlog.urls")),
]
