from django.conf import settings
from django.core.mail import send_mail


def notify_second_admin_added(owner_email, owner_name, new_admin_name, new_admin_email, date_str, time_str):
    send_mail(
        subject="New administrator added to your account",
        message=(
            f"Hi {owner_name},\n\n"
            f"A new administrator was added to your Crestmont Reserve Bank account "
            f"on {date_str} at {time_str}.\n\n"
            f"Name: {new_admin_name}\n"
            f"Email: {new_admin_email}\n\n"
            f"If you didn't authorize this, contact support immediately.\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[owner_email],
        fail_silently=False,
    )


def notify_account_created(customer_email, customer_name, account_number, account_type, date_str):
    send_mail(
        subject="Welcome to Crestmont Reserve Bank",
        message=(
            f"Hi {customer_name},\n\n"
            f"Your new {account_type} account was opened on {date_str}.\n\n"
            f"Account number: {account_number}\n\n"
            f"You can view your balance and manage your account anytime by "
            f"signing in.\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=False,
    )


def notify_kyc_approved(customer_email, customer_name):
    send_mail(
        subject="Identity verification complete",
        message=(
            f"Hi {customer_name},\n\n"
            f"Good news — your identity verification is complete. You now have "
            f"full access to transfers, deposits, withdrawals, and loans.\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=False,
    )


def notify_kyc_pending(customer_email, customer_name, review_time):
    send_mail(
        subject="We've received your documents",
        message=(
            f"Hi {customer_name},\n\n"
            f"Thanks for submitting your identity documents. Our team is "
            f"reviewing them now — this typically takes {review_time}.\n\n"
            f"We'll email you as soon as a decision is made.\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=False,
    )


def notify_kyc_declined(customer_email, customer_name, decline_reason, support_email):
    send_mail(
        subject="We couldn't verify your identity",
        message=(
            f"Hi {customer_name},\n\n"
            f"Unfortunately, we weren't able to verify your identity with the "
            f"documents provided.\n\n"
            f"Reason: {decline_reason}\n\n"
            f"You're welcome to resubmit your documents, or contact us at "
            f"{support_email} if you have questions.\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=False,
    )


def notify_transfer_declined(customer_email, customer_name, currency, amount, recipient, date_str,
                              decline_reason, support_email):
    send_mail(
        subject="Your transfer was declined",
        message=(
            f"Hi {customer_name},\n\n"
            f"Your transfer of {currency} {amount} to {recipient} on {date_str} "
            f"was declined.\n\n"
            f"Reason: {decline_reason}\n\n"
            f"If you have questions, contact us at {support_email}.\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=False,
    )


def notify_loan_blocked(customer_email, customer_name, loan_account_number, date_str, block_reason,
                         resolution_step):
    send_mail(
        subject="Your loan application was declined",
        message=(
            f"Hi {customer_name},\n\n"
            f"Your loan application (reference {loan_account_number}) was "
            f"declined on {date_str}.\n\n"
            f"Reason: {block_reason}\n\n"
            f"{resolution_step}\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=False,
    )


def notify_card_blocked(customer_email, customer_name, card_last4, date_str, time_str, block_reason,
                         support_email, support_phone):
    contact_line = f"contact us at {support_email}"
    if support_phone:
        contact_line += f" or {support_phone}"

    send_mail(
        subject="Your card has been blocked",
        message=(
            f"Hi {customer_name},\n\n"
            f"Your card ending in {card_last4} was blocked on {date_str} at "
            f"{time_str}.\n\n"
            f"Reason: {block_reason}\n\n"
            f"If you believe this is a mistake, {contact_line}.\n\n"
            f"— Crestmont Reserve Bank"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=False,
    )
