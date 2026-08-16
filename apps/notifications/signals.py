from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.banking.models import Account, Card, WithdrawalRequest
from apps.kyc.models import KYCDocument
from apps.loans.models import LoanApplication
from apps.users.models import Role, User

from .notifications import (
    notify_account_created,
    notify_card_blocked,
    notify_kyc_approved,
    notify_kyc_declined,
    notify_kyc_pending,
    notify_loan_blocked,
    notify_second_admin_added,
    notify_transfer_declined,
)

ADMIN_ROLES = (Role.ADMIN, Role.SUPERADMIN)
SUPPORT_EMAIL = getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)
SUPPORT_PHONE = getattr(settings, "SUPPORT_PHONE", "")
KYC_REVIEW_SLA_TEXT = getattr(settings, "KYC_REVIEW_SLA_TEXT", "a few business days")


def _display_name(user):
    return user.get_full_name() or user.email


# ---------------------------------------------------------------------------
# Second admin added — fires both when a new user is created directly as an
# admin, and when an existing user is promoted (role changes into
# ADMIN_ROLES). Recipient is looked up by role, not is_superuser: this app's
# permission classes (IsStaff/IsApprover/IsConfigManager) are role-based and
# nothing in the app ever sets Django's is_superuser flag, so filtering on
# it would never match anyone.
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=User)
def stash_previous_user_role(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_role = (
            User.objects.filter(pk=instance.pk).values_list("role", flat=True).first()
        )
    else:
        instance._previous_role = None


@receiver(post_save, sender=User)
def on_admin_user_created(sender, instance, created, **kwargs):
    was_admin = getattr(instance, "_previous_role", None) in ADMIN_ROLES
    is_admin = instance.role in ADMIN_ROLES
    if not is_admin or was_admin:
        return

    owner = (
        User.objects.filter(role=Role.SUPERADMIN)
        .exclude(pk=instance.pk)
        .order_by("date_joined")
        .first()
        or User.objects.filter(role=Role.ADMIN)
        .exclude(pk=instance.pk)
        .order_by("date_joined")
        .first()
    )
    if owner is None:
        return

    now = timezone.localtime()
    notify_second_admin_added(
        owner_email=owner.email,
        owner_name=_display_name(owner),
        new_admin_name=_display_name(instance),
        new_admin_email=instance.email,
        date_str=now.strftime("%B %d, %Y"),
        time_str=now.strftime("%I:%M %p %Z"),
    )


# ---------------------------------------------------------------------------
# Account created
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Account)
def on_account_created(sender, instance, created, **kwargs):
    if not created:
        return
    notify_account_created(
        customer_email=instance.owner.email,
        customer_name=_display_name(instance.owner),
        account_number=instance.account_number,
        account_type=instance.get_type_display(),
        date_str=timezone.localtime(instance.created_at).strftime("%B %d, %Y"),
    )


# ---------------------------------------------------------------------------
# KYC status change (KYCDocument, not User.kyc_status directly — this is
# where rejection_reason and the pending/approved/rejected transitions
# actually live)
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=KYCDocument)
def stash_previous_kyc_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = (
            KYCDocument.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._previous_status = None


@receiver(post_save, sender=KYCDocument)
def on_kyc_document_status_change(sender, instance, created, **kwargs):
    customer = instance.user
    customer_email = customer.email
    customer_name = _display_name(customer)

    if created:
        notify_kyc_pending(
            customer_email=customer_email,
            customer_name=customer_name,
            review_time=KYC_REVIEW_SLA_TEXT,
        )
        return

    previous_status = getattr(instance, "_previous_status", None)
    if previous_status == instance.status:
        return

    if instance.status == KYCDocument.Status.APPROVED:
        notify_kyc_approved(customer_email=customer_email, customer_name=customer_name)
    elif instance.status == KYCDocument.Status.REJECTED:
        notify_kyc_declined(
            customer_email=customer_email,
            customer_name=customer_name,
            decline_reason=instance.rejection_reason,
            support_email=SUPPORT_EMAIL,
        )


# ---------------------------------------------------------------------------
# "Transfer declined" — Transfer itself has no decline/reject path (it's
# always created directly as POSTED). The real declined-money-movement flow
# is WithdrawalRequest -> AdminWithdrawalRejectView, which is what this is
# wired to. notify_transfer_declined's parameter names describe the event,
# not the exact model it comes from.
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=WithdrawalRequest)
def stash_previous_withdrawal_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = (
            WithdrawalRequest.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._previous_status = None


@receiver(post_save, sender=WithdrawalRequest)
def on_withdrawal_declined(sender, instance, created, **kwargs):
    if created:
        return
    previous_status = getattr(instance, "_previous_status", None)
    if previous_status == instance.status or instance.status != WithdrawalRequest.Status.REJECTED:
        return

    account = instance.account
    notify_transfer_declined(
        customer_email=account.owner.email,
        customer_name=_display_name(account.owner),
        currency=account.currency,
        amount=f"{instance.amount_cents / 100:,.2f}",
        recipient=f"account ending {instance.destination_account_number[-4:]}",
        date_str=timezone.localtime().strftime("%B %d, %Y"),
        decline_reason=instance.rejection_reason,
        support_email=SUPPORT_EMAIL,
    )


# ---------------------------------------------------------------------------
# "Loan blocked" — LoanApplication has no "blocked" status; the real decline
# flow is AdminLoanRejectView -> status=REJECTED. There's also no account
# number until a loan is disbursed, so a short reference code built from the
# application id stands in for loan_account_number.
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=LoanApplication)
def stash_previous_loan_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = (
            LoanApplication.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._previous_status = None


@receiver(post_save, sender=LoanApplication)
def on_loan_rejected(sender, instance, created, **kwargs):
    if created:
        return
    previous_status = getattr(instance, "_previous_status", None)
    if previous_status == instance.status or instance.status != LoanApplication.Status.REJECTED:
        return

    applicant = instance.applicant
    notify_loan_blocked(
        customer_email=applicant.email,
        customer_name=_display_name(applicant),
        loan_account_number=str(instance.id)[:8].upper(),
        date_str=timezone.localtime().strftime("%B %d, %Y"),
        block_reason=instance.rejection_reason,
        resolution_step=f"Contact {SUPPORT_EMAIL} if you'd like to discuss this decision or reapply.",
    )


# ---------------------------------------------------------------------------
# Card blocked — fires when AdminCardBlockView sets Card.status=BLOCKED.
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=Card)
def stash_previous_card_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = (
            Card.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._previous_status = None


@receiver(post_save, sender=Card)
def on_card_blocked(sender, instance, created, **kwargs):
    if created:
        return
    previous_status = getattr(instance, "_previous_status", None)
    if previous_status == instance.status or instance.status != Card.Status.BLOCKED:
        return

    owner = instance.account.owner
    now = timezone.localtime()
    notify_card_blocked(
        customer_email=owner.email,
        customer_name=_display_name(owner),
        card_last4=instance.last4,
        date_str=now.strftime("%B %d, %Y"),
        time_str=now.strftime("%I:%M %p %Z"),
        block_reason=instance.block_reason or "Suspicious activity detected on this card.",
        support_email=SUPPORT_EMAIL,
        support_phone=SUPPORT_PHONE,
    )
