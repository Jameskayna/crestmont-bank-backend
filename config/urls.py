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
    # Later stages will add:
    # path("loans/", include("apps.loans.urls")),
    # path("kyc/", include("apps.kyc.urls")),
    # path("notifications/", include("apps.notifications.urls")),
]
