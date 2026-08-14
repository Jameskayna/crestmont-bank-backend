from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from apps.auditlog.utils import log_action
from apps.notifications.models import Notification
from apps.users.models import KYCStatus
from apps.users.permissions import IsStaff

from .models import KYCDocument
from .serializers import AdminKYCDocumentSerializer, KYCDocumentSerializer, KYCDocumentUploadSerializer


class KYCDocumentListCreateView(APIView):
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "kyc"

    def get(self, request):
        docs = KYCDocument.objects.filter(user=request.user).order_by("-uploaded_at")
        return Response(KYCDocumentSerializer(docs, many=True).data)

    def post(self, request):
        serializer = KYCDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            doc = KYCDocument.objects.create(user=request.user, **serializer.validated_data)
            # A fresh submission (or resubmission after rejection) puts the
            # user back in the review queue. An already-verified user isn't
            # bumped back to pending just for adding another document type.
            if request.user.kyc_status in (KYCStatus.UNVERIFIED, KYCStatus.REJECTED):
                request.user.kyc_status = KYCStatus.PENDING
                request.user.save(update_fields=["kyc_status"])
            Notification.objects.create(
                user=request.user,
                category=Notification.Category.KYC,
                title="Document submitted",
                body=f"Your {doc.get_doc_type_display()} has been submitted for review.",
            )

        return Response(KYCDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class AdminKYCDocumentListView(APIView):
    """The KYC review queue, nested under Users & Accounts per the support
    role's stated capability ('can view accounts, verify KYC')."""

    permission_classes = [IsStaff]

    def get(self, request):
        docs = KYCDocument.objects.filter(status=KYCDocument.Status.PENDING).select_related("user").order_by(
            "uploaded_at"
        )
        return Response(AdminKYCDocumentSerializer(docs, many=True).data)


class AdminKYCApproveView(APIView):
    permission_classes = [IsStaff]

    def post(self, request, pk):
        doc = get_object_or_404(KYCDocument, pk=pk)
        doc.status = KYCDocument.Status.APPROVED
        doc.reviewed_by = request.user
        doc.reviewed_at = timezone.now()
        doc.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        user = doc.user
        user.kyc_status = KYCStatus.VERIFIED
        user.save(update_fields=["kyc_status"])
        Notification.objects.create(
            user=user,
            category=Notification.Category.KYC,
            title="Identity verified",
            body="Your identity verification is complete.",
        )
        log_action(request, "kyc.approve", "KYCDocument", doc.id)
        return Response(AdminKYCDocumentSerializer(doc).data)


class AdminKYCRejectView(APIView):
    permission_classes = [IsStaff]

    def post(self, request, pk):
        doc = get_object_or_404(KYCDocument, pk=pk)
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        doc.status = KYCDocument.Status.REJECTED
        doc.reviewed_by = request.user
        doc.reviewed_at = timezone.now()
        doc.rejection_reason = reason
        doc.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])

        user = doc.user
        user.kyc_status = KYCStatus.REJECTED
        user.save(update_fields=["kyc_status"])
        Notification.objects.create(
            user=user, category=Notification.Category.KYC, title="Document rejected", body=reason
        )
        log_action(request, "kyc.reject", "KYCDocument", doc.id, reason=reason)
        return Response(AdminKYCDocumentSerializer(doc).data)
