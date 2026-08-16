import secrets
from datetime import date

from .models import Account


def generate_account_number():
    """12-digit numeric US-style account number, retried until unique."""
    while True:
        number = "".join(secrets.choice("0123456789") for _ in range(12))
        if not Account.objects.filter(account_number=number).exists():
            return number


def generate_card_details():
    """Simulated card-issuer response for AdminCardApproveView — a real
    integration (Stripe Issuing, Marqeta) would return these instead.
    Expiry is 4 years out, matching typical card validity."""
    last4 = "".join(secrets.choice("0123456789") for _ in range(4))
    provider_card_id = f"sim_{secrets.token_hex(8)}"
    today = date.today()
    return {
        "provider_card_id": provider_card_id,
        "last4": last4,
        "expiry_month": today.month,
        "expiry_year": today.year + 4,
    }
