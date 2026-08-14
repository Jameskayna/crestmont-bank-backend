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
    # Later stages will add:
    # path("loans/", include("apps.loans.urls")),
]
