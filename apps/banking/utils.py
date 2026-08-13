import secrets

from .models import Account


def generate_account_number():
    """12-digit numeric US-style account number, retried until unique."""
    while True:
        number = "".join(secrets.choice("0123456789") for _ in range(12))
        if not Account.objects.filter(account_number=number).exists():
            return number
