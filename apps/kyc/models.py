import uuid
from django.conf import settings
from django.db import models


def kyc_upload_path(instance, filename):
    # Namespaced by user id so files aren't guessable/enumerable.
    return f"kyc/{instance.user_id}/{uuid.uuid4()}_{filename}"


class KYCDocument(models.Model):
    class DocType(models.TextChoices):
        PASSPORT = "passport", "Passport"
        NATIONAL_ID = "national_id", "National ID card"
        DRIVERS_LICENSE = "drivers_license", "Driver's licence"
        PROOF_OF_ADDRESS = "proof_of_address", "Proof of address"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kyc_documents")
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    # Stored in private object storage (S3 with no public ACL), never
    # served directly — always via a short-lived signed URL generated
    # for a verified staff member.
    file = models.FileField(upload_to=kyc_upload_path)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    rejection_reason = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
