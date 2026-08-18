from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("register", views.RegisterView.as_view(), name="register"),
    path("verify-email", views.VerifyEmailView.as_view(), name="verify-email"),
    path("login", views.LoginView.as_view(), name="login"),
    path("login/verify-otp", views.LoginOtpVerifyView.as_view(), name="login-verify-otp"),
    path("login/resend-otp", views.LoginOtpResendView.as_view(), name="login-resend-otp"),
    path("token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("me", views.RefreshMeView.as_view(), name="me"),
    path("password-reset/request", views.PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/confirm", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("2fa/setup", views.TwoFactorSetupView.as_view(), name="2fa-setup"),
    path("2fa/confirm", views.TwoFactorConfirmView.as_view(), name="2fa-confirm"),
    path("2fa/disable", views.TwoFactorDisableView.as_view(), name="2fa-disable"),
]
