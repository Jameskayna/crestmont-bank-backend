from django.db import transaction
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.notifications.models import Notification
from apps.users.models import KYCStatus

from .models import KYCDocument
from .serializers import KYCDocumentSerializer, KYCDocumentUploadSerializer


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
