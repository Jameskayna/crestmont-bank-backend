from rest_framework import serializers

from .models import Notice, Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "category", "title", "body", "is_read", "created_at"]
        read_only_fields = fields


class NoticeTargetUserSerializer(serializers.Serializer):
    """Minimal user shape for rendering target_users chips in the staff
    notice form — not the full UserSerializer, which is more than this
    needs and would leak more than it should."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class NoticeSerializer(serializers.ModelSerializer):
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)
    target_users = NoticeTargetUserSerializer(many=True, read_only=True)

    class Meta:
        model = Notice
        fields = [
            "id", "title", "message", "severity", "audience", "target_users", "is_active",
            "created_by_email", "created_at", "updated_at",
        ]
        read_only_fields = fields


class NoticeWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    message = serializers.CharField()
    severity = serializers.ChoiceField(choices=Notice.Severity.choices, required=False, default=Notice.Severity.INFO)
    audience = serializers.ChoiceField(choices=Notice.Audience.choices, required=False, default=Notice.Audience.ALL)
    target_user_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, data):
        # Guard with "in" rather than .get(...), since under partial=True
        # (PATCH) an unset field is simply absent from data, not defaulted —
        # only actually re-validate when the caller is touching audience.
        if data.get("audience") == Notice.Audience.SPECIFIC and not data.get("target_user_ids"):
            raise serializers.ValidationError("Select at least one user for a specific-users notice.")
        return data
