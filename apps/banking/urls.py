from django.urls import path

from . import views

urlpatterns = [
    path("accounts", views.AccountListCreateView.as_view(), name="account-list-create"),
    path("accounts/<uuid:pk>/transactions", views.AccountTransactionsView.as_view(), name="account-transactions"),
    path("transfers", views.TransferCreateView.as_view(), name="transfer-create"),
]
