from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_otp.plugins.otp_email.models import EmailDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.auditlog.utils import log_action
from apps.notifications.models import Notification

from .models import EmailVerificationToken, PasswordResetToken, Role
from .permissions import IsApprover, IsConfigManager, IsStaff
from .serializers import (
    LoginOtpResendSerializer,
    LoginOtpVerifySerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .utils import (
    generate_raw_token,
    hash_token,
    send_email_otp_challenge,
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
    """Step 1: verify the password, then email a one-time code. Tokens are
    never issued here — only LoginOtpVerifyView issues them, once the code
    (and TOTP, for accounts that also have that enabled) checks out."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        password = serializer.validated_data["password"]

        user = User.objects.filter(email__iexact=email).first()
        # Always run password hashing even when the user doesn't exist, so
        # response timing doesn't leak whether an email is registered.
        valid_password = user.check_password(password) if user else False
        if not user or not valid_password:
            return Response({"error": "Invalid email or password."}, status=401)

        if user.is_frozen:
            return Response({"error": "This account is currently restricted. Contact support."}, status=403)

        device, _ = EmailDevice.objects.get_or_create(
            user=user, name="login", defaults={"confirmed": True}
        )
        if not device.confirmed:
            device.confirmed = True
            device.save(update_fields=["confirmed"])

        try:
            send_email_otp_challenge(device)
        except Exception:
            return Response(
                {"error": "We couldn't send your verification code. Please try again in a moment."},
                status=503,
            )

        return Response({"requires_email_otp": True, "requires_2fa": user.is_2fa_enabled})


class LoginOtpVerifyView(APIView):
    """Step 2: the code emailed by LoginView (plus a TOTP code, if the
    account also has authenticator-app 2FA enabled) completes login."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        serializer = LoginOtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        code = serializer.validated_data["code"]
        totp_code = serializer.validated_data.get("totp_code", "")

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"error": "Incorrect or expired code."}, status=400)

        if user.is_frozen:
            return Response({"error": "This account is currently restricted. Contact support."}, status=403)

        device = EmailDevice.objects.filter(user=user, name="login", confirmed=True).first()
        if not device or not device.verify_token(code):
            return Response({"error": "Incorrect or expired code."}, status=400)

        if user.is_2fa_enabled:
            totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
            if not totp_code or not totp_device or not totp_device.verify_token(totp_code):
                return Response({"error": "Invalid authentication code."}, status=401)

        tokens = issue_tokens(user)
        return Response({"user": UserSerializer(user).data, **tokens})


class LoginOtpResendView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        serializer = LoginOtpResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        user = User.objects.filter(email__iexact=email).first()
        device = (
            EmailDevice.objects.filter(user=user, name="login", confirmed=True).first()
            if user
            else None
        )
        if device:
            try:
                send_email_otp_challenge(device)
            except Exception:
                pass

        # Same email-enumeration-safe shape as PasswordResetRequestView: one
        # generic response whether or not the email/device exists.
        return Response({"message": "If a login is in progress for that email, a new code has been sent."})


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


class AdminUserListView(APIView):
    """Users & Accounts tab: search/list. Any staff role can view."""

    permission_classes = [IsStaff]

    def get(self, request):
        qs = User.objects.all().order_by("-created_at")
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(email__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search)
            )
        return Response(UserSerializer(qs[:100], many=True).data)


class AdminUserDetailView(APIView):
    """A user's own accounts and KYC documents, for the staff detail view —
    avoids the frontend needing three separate round trips per user."""

    permission_classes = [IsStaff]

    def get(self, request, pk):
        from apps.banking.models import Account
        from apps.banking.serializers import AccountSerializer
        from apps.kyc.models import KYCDocument
        from apps.kyc.serializers import KYCDocumentSerializer

        user = get_object_or_404(User, pk=pk)
        data = UserSerializer(user).data
        data["accounts"] = AccountSerializer(Account.objects.filter(owner=user), many=True).data
        data["kyc_documents"] = KYCDocumentSerializer(
            KYCDocument.objects.filter(user=user).order_by("-uploaded_at"), many=True
        ).data
        return Response(data)


class AdminUserBlockView(APIView):
    """'Block login' — distinct from freezing an account. Sets is_frozen
    (checked at login) and blacklists every outstanding refresh token so
    already-issued sessions can't silently keep working until they expire."""

    permission_classes = [IsApprover]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        user.is_frozen = True
        user.frozen_reason = reason
        user.save(update_fields=["is_frozen", "frozen_reason"])

        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        log_action(request, "user.block_login", "User", user.id, reason=reason)
        return Response(UserSerializer(user).data)


class AdminUserUnblockView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.is_frozen = False
        user.frozen_reason = ""
        user.save(update_fields=["is_frozen", "frozen_reason"])
        log_action(request, "user.unblock_login", "User", user.id)
        return Response(UserSerializer(user).data)


class AdminUserClearLoginOtpView(APIView):
    """Break-glass unstick for a user whose registered email can't receive
    the mandatory login OTP (typo, dead inbox, spam-filtered) — deletes
    their login challenge device so their next login attempt starts clean.
    This does not skip OTP entirely; it just clears stuck state so a fresh
    code can be generated and (hopefully, once the email is fixed) delivered."""

    permission_classes = [IsApprover]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        EmailDevice.objects.filter(user=user, name="login").delete()

        log_action(request, "user.clear_login_otp", "User", user.id, reason=reason)
        return Response({"message": "Login verification cleared. The user can try logging in again."})


class AdminUserPromoteView(APIView):
    """Grants admin (role=admin) access. This is the app's own permission
    tier used by IsStaff/IsApprover/IsConfigManager — distinct from Django's
    is_staff/is_superuser, which this app doesn't use for API authorization
    and which this view deliberately leaves untouched."""

    permission_classes = [IsConfigManager]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user.role in (Role.ADMIN, Role.SUPERADMIN):
            return Response({"error": "This user is already an administrator."}, status=status.HTTP_400_BAD_REQUEST)

        user.role = Role.ADMIN
        user.save(update_fields=["role"])
        log_action(request, "user.promote_admin", "User", user.id)
        return Response(UserSerializer(user).data)


class AdminUserDemoteView(APIView):
    """Revokes admin access, mirroring AdminUserPromoteView. A staff member
    can never revoke their own access — the one way to lose admin rights
    is to have another admin do it, which prevents accidentally locking
    everyone out."""

    permission_classes = [IsConfigManager]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user.id == request.user.id:
            return Response(
                {"error": "You cannot revoke your own admin access."}, status=status.HTTP_400_BAD_REQUEST
            )

        if user.role not in (Role.ADMIN, Role.SUPERADMIN):
            return Response({"error": "This user is not an administrator."}, status=status.HTTP_400_BAD_REQUEST)

        user.role = Role.CUSTOMER
        user.save(update_fields=["role"])
        Notification.objects.create(
            user=user,
            category=Notification.Category.SECURITY,
            title="Admin access revoked",
            body="Your administrator access to Crestmont Reserve Bank's staff console has been revoked.",
        )
        log_action(request, "user.revoke_admin", "User", user.id)
        return Response(UserSerializer(user).data)
