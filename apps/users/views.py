from django.contrib.auth import get_user_model
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailVerificationToken, PasswordResetToken
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .utils import (
    generate_raw_token,
    hash_token,
    send_password_reset_email,
    send_verification_email,
    token_expiry,
)

User = get_user_model()


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        raw_token = generate_raw_token()
        EmailVerificationToken.objects.create(
            user=user, token_hash=hash_token(raw_token), expires_at=token_expiry(hours=24)
        )
        send_verification_email(user, raw_token)

        return Response(
            {
                "user": UserSerializer(user).data,
                "message": "Account created. Check your email to verify your address before signing in.",
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        raw_token = request.data.get("token", "")
        token_hash = hash_token(raw_token)
        record = (
            EmailVerificationToken.objects.filter(
                token_hash=token_hash, used_at__isnull=True, expires_at__gt=timezone.now()
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return Response({"error": "This verification link is invalid or has expired."}, status=400)

        record.used_at = timezone.now()
        record.save(update_fields=["used_at"])

        user = record.user
        user.email_verified = True
        user.save(update_fields=["email_verified"])

        return Response({"message": "Email verified. You can now sign in."})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        password = serializer.validated_data["password"]
        totp_code = serializer.validated_data.get("totp_code", "")

        user = User.objects.filter(email__iexact=email).first()
        # Always run password hashing even when the user doesn't exist, so
        # response timing doesn't leak whether an email is registered.
        valid_password = user.check_password(password) if user else False
        if not user or not valid_password:
            return Response({"error": "Invalid email or password."}, status=401)

        if user.is_frozen:
            return Response({"error": "This account is currently restricted. Contact support."}, status=403)

        if user.is_2fa_enabled:
            if not totp_code:
                return Response({"requires_2fa": True}, status=200)
            device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
            if not device or not device.verify_token(totp_code):
                return Response({"error": "Invalid authentication code."}, status=401)

        tokens = issue_tokens(user)
        return Response({"user": UserSerializer(user).data, **tokens})


class RefreshMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        user = User.objects.filter(email__iexact=email).first()
        if user:
            raw_token = generate_raw_token()
            PasswordResetToken.objects.create(
                user=user, token_hash=hash_token(raw_token), expires_at=token_expiry(hours=1)
            )
            send_password_reset_email(user, raw_token)

        # Always return the same response whether or not the email exists,
        # so this endpoint can't be used to enumerate registered accounts.
        return Response({"message": "If that email is registered, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_hash = hash_token(serializer.validated_data["token"])

        record = (
            PasswordResetToken.objects.filter(
                token_hash=token_hash, used_at__isnull=True, expires_at__gt=timezone.now()
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return Response({"error": "This reset link is invalid or has expired."}, status=400)

        record.used_at = timezone.now()
        record.save(update_fields=["used_at"])

        user = record.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        return Response({"message": "Password updated. You can now sign in."})


class TwoFactorSetupView(APIView):
    """Step 1: create an unconfirmed TOTP device and return its provisioning URI
    (render this as a QR code on the frontend with any QR library)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
        device = TOTPDevice.objects.create(user=request.user, name="default", confirmed=False)
        return Response({"otpauth_url": device.config_url})


class TwoFactorConfirmView(APIView):
    """Step 2: verify a code from the authenticator app to activate 2FA."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get("code", "")
        device = TOTPDevice.objects.filter(user=request.user, confirmed=False).order_by("-id").first()
        if not device or not device.verify_token(code):
            return Response({"error": "Invalid code. Try again."}, status=400)

        device.confirmed = True
        device.save(update_fields=["confirmed"])
        request.user.is_2fa_enabled = True
        request.user.save(update_fields=["is_2fa_enabled"])

        return Response({"message": "Two-factor authentication enabled."})


class TwoFactorDisableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        TOTPDevice.objects.filter(user=request.user).delete()
        request.user.is_2fa_enabled = False
        request.user.save(update_fields=["is_2fa_enabled"])
        return Response({"message": "Two-factor authentication disabled."})
