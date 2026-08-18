from django.urls import path

from . import views

urlpatterns = [
    path("accounts", views.AccountListCreateView.as_view(), name="account-list-create"),
    path("accounts/<uuid:pk>/transactions", views.AccountTransactionsView.as_view(), name="account-transactions"),
    path("cards", views.CardListCreateView.as_view(), name="card-list-create"),
    path("transfers/initiate", views.TransferInitiateView.as_view(), name="transfer-initiate"),
    path("transfers/confirm", views.TransferConfirmView.as_view(), name="transfer-confirm"),
    path("transfers/resend", views.TransferResendOtpView.as_view(), name="transfer-resend-otp"),
    path("deposits", views.DepositListCreateView.as_view(), name="deposit-list-create"),
    path("withdrawals", views.WithdrawalListCreateView.as_view(), name="withdrawal-list-create"),
    path("webhooks/stripe", views.StripeWebhookView.as_view(), name="stripe-webhook"),
]
