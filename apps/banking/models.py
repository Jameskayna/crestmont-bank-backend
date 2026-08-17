import uuid
from decouple import config
from django.conf import settings
from django.db import models


class AccountType(models.TextChoices):
    CHECKING = "checking", "Checking"
    SAVINGS = "savings", "Savings"
    CREDIT = "credit", "Credit"


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FROZEN = "frozen", "Frozen"
    CLOSED = "closed", "Closed"


class Account(models.Model):
    """
    Balances are NEVER stored directly — they're derived by summing
    LedgerEntry rows (see Account.balance_cents). This keeps the ledger
    append-only and auditable: nothing can silently overwrite history,
    and every cent is traceable to the entry that produced it.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="accounts")
    account_number = models.CharField(max_length=17, unique=True)  # generated on creation, US-style account number
    routing_number = models.CharField(max_length=9, blank=True)  # ABA routing number, set once provisioned at the BaaS partner
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=AccountType.choices)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.ACTIVE)

    # Populated once this account is provisioned at the BaaS partner.
    # NULL while running against Stripe-only funding without a partner bank.
    provider_account_id = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["owner"]), models.Index(fields=["account_number"])]

    def __str__(self):
        return f"{self.name} ({self.account_number})"

    def balance_cents(self):
        result = self.ledger_entries.filter(status="posted").aggregate(total=models.Sum("amount_cents"))
        return result["total"] or 0

    def held_cents(self):
        """Sum of pending (not yet posted) ledger entries — holds are negative amounts."""
        result = self.ledger_entries.filter(status="pending").aggregate(total=models.Sum("amount_cents"))
        return result["total"] or 0

    def available_cents(self):
        """Posted balance minus outstanding holds, e.g. a withdrawal awaiting Stripe confirmation."""
        return self.balance_cents() + self.held_cents()


class LedgerEntry(models.Model):
    """
    Append-only. A row is written by the system in response to a real
    event (a posted transfer, a settled Stripe deposit, an approved
    manual adjustment) — never edited by hand and never deleted.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        POSTED = "posted", "Posted"
        FAILED = "failed", "Failed"

    class SourceType(models.TextChoices):
        TRANSFER = "transfer", "Internal transfer"
        DEPOSIT = "deposit", "Deposit (Stripe)"
        WITHDRAWAL = "withdrawal", "Withdrawal (Stripe)"
        LOAN_DISBURSEMENT = "loan_disbursement", "Loan disbursement"
        LOAN_REPAYMENT = "loan_repayment", "Loan repayment"
        MANUAL_ADJUSTMENT = "manual_adjustment", "Manual adjustment"
        INTEREST = "interest", "Interest"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="ledger_entries")
    amount_cents = models.BigIntegerField()  # positive = credit, negative = debit
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)

    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    source_id = models.UUIDField()  # points at the Transfer/Deposit/Withdrawal/ManualAdjustment row

    provider_ref = models.CharField(max_length=120, blank=True)  # e.g. Stripe payment_intent id
    created_at = models.DateTimeField(auto_now_add=True)

    # Set only when this entry records something that happened on an
    # earlier date than when it was entered (a backdated manual
    # adjustment) — null means "same day as created_at". created_at
    # itself is never touched: it stays the true, append-only record of
    # when the entry was actually written.
    transaction_date = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["account", "-created_at"]),
            models.Index(fields=["source_type", "source_id"]),
        ]


class Transfer(models.Model):
    """Internal transfer between two accounts on the platform."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        POSTED = "posted", "Posted"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="outgoing_transfers")
    to_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="incoming_transfers")
    amount_cents = models.BigIntegerField()
    note = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)


class DepositRequest(models.Model):
    """Funding an account from an external card/bank via Stripe."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="deposit_requests")
    amount_cents = models.BigIntegerField()
    stripe_payment_intent_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class WithdrawalRequest(models.Model):
    """Paying an account's funds out to the user's external bank via Stripe payouts."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"        # queued for compliance review above a threshold
        APPROVED = "approved", "Approved"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    # Above this, held for compliance review before Stripe is called. Same
    # config()-from-.env pattern as other tunables in config/settings.py;
    # defaults to $500 if WITHDRAWAL_AUTO_APPROVE_LIMIT_CENTS isn't set.
    AUTO_APPROVE_LIMIT_CENTS = config("WITHDRAWAL_AUTO_APPROVE_LIMIT_CENTS", default=50_000, cast=int)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="withdrawal_requests")
    amount_cents = models.BigIntegerField()
    destination_account_number = models.CharField(max_length=17)
    destination_routing_number = models.CharField(max_length=9)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    rejection_reason = models.CharField(max_length=255, blank=True)
    stripe_payout_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Card(models.Model):
    """
    Rows start life as a customer request (PENDING, no issued details yet)
    and only gain provider_card_id/last4/expiry once staff approves —
    same shape as LoanApplication separating requested terms from what's
    only known at approval time.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"
        BLOCKED = "blocked", "Blocked"
        EXPIRED = "expired", "Expired"

    class Brand(models.TextChoices):
        VISA = "visa", "Visa"
        MASTERCARD = "mastercard", "Mastercard"
        VERVE = "verve", "Verve"

    class CardType(models.TextChoices):
        DEBIT = "debit", "Debit"
        CREDIT = "credit", "Credit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="cards")
    # Real PANs are NEVER stored in your own DB — a card issuing partner
    # (Stripe Issuing, Marqeta, or your BaaS partner) tokenizes and returns
    # only a reference plus the last 4 digits for display. Both blank until
    # the request is approved and a card is actually issued.
    provider_card_id = models.CharField(max_length=120, blank=True)
    last4 = models.CharField(max_length=4, blank=True)
    brand = models.CharField(max_length=20, choices=Brand.choices)
    card_type = models.CharField(max_length=10, choices=CardType.choices, default=CardType.DEBIT)
    expiry_month = models.PositiveSmallIntegerField(null=True, blank=True)
    expiry_year = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    block_reason = models.CharField(max_length=255, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class ManualAdjustment(models.Model):
    """
    The controlled replacement for a free-form 'admin credit/debit'
    button. Every adjustment requires a reason and an authorizing staff
    member, is capped, and (above AUTO_APPROVE_LIMIT_CENTS) needs a second
    approver before it posts a LedgerEntry. This is what real banks use
    for refunds, fee reversals, and dispute resolutions.
    """
    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending second approval"
        POSTED = "posted", "Posted"
        REJECTED = "rejected", "Rejected"

    AUTO_APPROVE_LIMIT_CENTS = 10_000  # $100 — above this, needs a second approver
    MAX_BACKDATE_DAYS = 90  # how far in the past transaction_date is allowed to be

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="manual_adjustments")
    amount_cents = models.BigIntegerField()  # positive = credit, negative = debit
    reason = models.CharField(max_length=255)
    # Set when this adjustment records something that actually happened
    # earlier (e.g. an unlogged wire transfer) — null means "today".
    # Bounded by MAX_BACKDATE_DAYS and the account's own created_at; see
    # ManualAdjustmentCreateSerializer / AdminAdjustmentListCreateView.
    transaction_date = models.DateField(null=True, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_APPROVAL)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
