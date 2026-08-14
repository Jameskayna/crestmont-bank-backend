from django.urls import path

from . import views

urlpatterns = [
    path("loans/products", views.LoanProductListView.as_view(), name="loan-product-list"),
    path("loans/applications", views.LoanApplicationListCreateView.as_view(), name="loan-application-list-create"),
]
