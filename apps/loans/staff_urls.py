from django.urls import path

from . import views

urlpatterns = [
    path(
        "staff/loans/applications",
        views.AdminLoanApplicationListView.as_view(),
        name="staff-loan-application-list",
    ),
    path(
        "staff/loans/applications/<uuid:pk>/approve",
        views.AdminLoanApproveView.as_view(),
        name="staff-loan-application-approve",
    ),
    path(
        "staff/loans/applications/<uuid:pk>/reject",
        views.AdminLoanRejectView.as_view(),
        name="staff-loan-application-reject",
    ),
    path(
        "staff/loan-products",
        views.AdminLoanProductListCreateView.as_view(),
        name="staff-loan-product-list-create",
    ),
    path(
        "staff/loan-products/<uuid:pk>",
        views.AdminLoanProductDetailView.as_view(),
        name="staff-loan-product-detail",
    ),
]
