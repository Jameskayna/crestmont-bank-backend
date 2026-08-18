import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def send_email_otp_challenge(device):
    """Generate and email an OTP for a django_otp EmailDevice.

    EmailDevice.generate_challenge() persists the new token (and starts its
    resend cooldown) *before* it sends the email. If the send then raises,
    the device is left holding a code the user never received, plus a live
    cooldown that would block them from getting a working one for another
    60s. Since that's entirely our failure, not theirs, we undo both here
    so the very next attempt isn't punished by a code they never saw.
    """
    try:
        device.generate_challenge()
    except Exception:
        device.token = None
        device.cooldown_reset(commit=False)
        device.save()
        raise


def generate_raw_token():
    """A high-entropy token that's only ever transmitted via email, never stored raw."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


def token_expiry(hours=0, minutes=0, days=0):
    return timezone.now() + timedelta(hours=hours, minutes=minutes, days=days)


def send_verification_email(user, raw_token):
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
    send_mail(
        subject="Verify your Crestmont Reserve Bank account",
        message=(
            f"Hi {user.first_name or user.email},\n\n"
            f"Confirm your email address to finish setting up your account:\n{verify_url}\n\n"
            "This link expires in 24 hours. If you didn't create a Crestmont account, "
            "you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def send_password_reset_email(user, raw_token):
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    send_mail(
        subject="Reset your Crestmont Reserve Bank password",
        message=(
            f"Hi {user.first_name or user.email},\n\n"
            f"Reset your password using this link:\n{reset_url}\n\n"
            "This link expires in 1 hour. If you didn't request this, you can safely "
            "ignore this email — your password won't be changed."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
