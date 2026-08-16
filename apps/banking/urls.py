from django.urls import path

from . import views

urlpatterns = [
    path("accounts", views.AccountListCreateView.as_view(), name="account-list-create"),
    path("accounts/<uuid:pk>/transactions", views.AccountTransactionsView.as_view(), name="account-transactions"),
    path("accounts/<uuid:pk>/cards", views.AccountCardsView.as_view(), name="account-cards"),
    path("transfers", views.TransferCreateView.as_view(), name="transfer-create"),
    path("deposits", views.DepositListCreateView.as_view(), name="deposit-list-create"),
    path("withdrawals", views.WithdrawalListCreateView.as_view(), name="withdrawal-list-create"),
    path("webhooks/stripe", views.StripeWebhookView.as_view(), name="stripe-webhook"),
]
