from django.urls import path

from . import views

urlpatterns = [
    path("staff/kyc/documents", views.AdminKYCDocumentListView.as_view(), name="staff-kyc-document-list"),
    path(
        "staff/kyc/documents/<uuid:pk>/approve",
        views.AdminKYCApproveView.as_view(),
        name="staff-kyc-document-approve",
    ),
    path(
        "staff/kyc/documents/<uuid:pk>/reject",
        views.AdminKYCRejectView.as_view(),
        name="staff-kyc-document-reject",
    ),
]
