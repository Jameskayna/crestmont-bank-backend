from rest_framework import serializers

from .models import Notice, Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "category", "title", "body", "is_read", "created_at"]
        read_only_fields = fields


class NoticeSerializer(serializers.ModelSerializer):
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = Notice
        fields = [
            "id", "title", "message", "severity", "is_active",
            "created_by_email", "created_at", "updated_at",
        ]
        read_only_fields = fields


class NoticeWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    message = serializers.CharField()
    severity = serializers.ChoiceField(choices=Notice.Severity.choices, required=False, default=Notice.Severity.INFO)
    is_active = serializers.BooleanField(required=False, default=True)
