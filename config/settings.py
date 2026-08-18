from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_email",
    "anymail",

    # domain apps
    "apps.users",
    "apps.banking",
    "apps.loans",
    "apps.kyc",
    "apps.notifications",
    "apps.auditlog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.auditlog.middleware.RequestAuditMiddleware",  # logs who-did-what, see Stage 3
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

import dj_database_url

DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL:
    # Render (and most PaaS providers) inject a single DATABASE_URL rather
    # than separate host/user/password variables.
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST"),
            "PORT": config("DB_PORT"),
        }
    }

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",       # login/register/reset attempts
        "otp": "5/min",         # 2FA code verification attempts
        "transfer": "20/min",
        "deposit": "10/min",
        "withdrawal": "10/min",
        "kyc": "10/min",
        "loan": "10/min",
    },
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("ACCESS_TOKEN_LIFETIME_MIN", default=15, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", cast=Csv())
CORS_ALLOW_CREDENTIALS = True

# CSRF is still relevant for the Django admin (session-auth based) even
# though the API itself uses JWT, which is not vulnerable to CSRF.
CSRF_TRUSTED_ORIGINS = config("CORS_ALLOWED_ORIGINS", cast=Csv())
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = config("EMAIL_BACKEND")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL")
# Zoho Mail via SMTP — Anymail doesn't support Zoho as an ESP, so this
# bypasses Anymail entirely and uses Django's built-in SMTP backend.
# These are only read when EMAIL_BACKEND is the smtp backend; the console
# backend (local dev) ignores them.
EMAIL_HOST = config("EMAIL_HOST", default="smtp.zoho.com")
EMAIL_PORT = config("EMAIL_PORT", default=465, cast=int)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=True, cast=bool)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

SUPPORT_EMAIL = config("SUPPORT_EMAIL", default=DEFAULT_FROM_EMAIL)
SUPPORT_PHONE = config("SUPPORT_PHONE", default="")
KYC_REVIEW_SLA_TEXT = config("KYC_REVIEW_SLA_TEXT", default="1-2 business days")

STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = config("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")

FRONTEND_URL = config("FRONTEND_URL")

# Label shown in authenticator apps (Google Authenticator, Authy, etc.)
# next to the account when a user scans the 2FA QR code.
OTP_TOTP_ISSUER = "Crestmont Reserve Bank"

# Mandatory email OTP (login + transfers). Delivery reuses EmailDevice's
# built-in django.core.mail.send_mail wrapper, so it goes through the same
# Zoho SMTP backend configured above with no extra plumbing.
OTP_EMAIL_SENDER = DEFAULT_FROM_EMAIL
OTP_EMAIL_SUBJECT = "Your Crestmont Reserve Bank verification code"
OTP_EMAIL_TOKEN_VALIDITY = 600  # 10 minutes
OTP_EMAIL_BODY_TEMPLATE = (
    "Hi,\n\n"
    "Your Crestmont Reserve Bank verification code is: {{ token }}\n\n"
    "This code expires in 10 minutes and can only be used once. "
    "If you didn't request this code, you can safely ignore this email."
)

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# KYCDocument.file lands here for now. Render's web service disk is
# ephemeral — this does NOT survive a redeploy or restart, so it's fine for
# local dev/testing only. Before real KYC documents from real users are
# collected, this needs to move to S3 (django-storages) or a Render Disk,
# per the private-object-storage design already assumed in apps/kyc/models.py.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
