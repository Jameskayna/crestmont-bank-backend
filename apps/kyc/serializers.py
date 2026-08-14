from rest_framework import serializers

from .models import KYCDocument

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


class KYCDocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCDocument
        fields = ["doc_type", "file"]

    def validate_file(self, value):
        if value.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("File must be under 10MB.")
        if getattr(value, "content_type", None) not in ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError("Only JPEG, PNG, or PDF files are accepted.")
        return value


class KYCDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCDocument
        fields = ["id", "doc_type", "status", "rejection_reason", "uploaded_at", "reviewed_at"]
        read_only_fields = fields


class AdminKYCDocumentSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = KYCDocument
        fields = ["id", "user_email", "doc_type", "status", "rejection_reason", "uploaded_at", "reviewed_at"]
        read_only_fields = fields
