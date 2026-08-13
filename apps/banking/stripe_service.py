import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_deposit_intent(*, amount_cents, currency, deposit_request_id, account_id):
    return stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency.lower(),
        automatic_payment_methods={"enabled": True},
        metadata={"deposit_request_id": str(deposit_request_id), "account_id": str(account_id)},
    )


def create_withdrawal_payout(*, amount_cents, currency, withdrawal_request_id, account_id):
    """
    Pays out from the platform's own Stripe balance. Routing funds to the
    *customer's* external bank account (destination_account_number below)
    needs Stripe Connect or Treasury, or a BaaS partner — same gap noted on
    Account.provider_account_id. This is the simplified stand-in so the
    approval/ledger flow has something real to call.
    """
    return stripe.Payout.create(
        amount=amount_cents,
        currency=currency.lower(),
        metadata={"withdrawal_request_id": str(withdrawal_request_id), "account_id": str(account_id)},
    )


def verify_webhook_event(payload, sig_header):
    return stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
