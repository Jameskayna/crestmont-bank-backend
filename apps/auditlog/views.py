from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsStaff

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        logs = AuditLog.objects.select_related("actor").order_by("-created_at")[:200]
        return Response(AuditLogSerializer(logs, many=True).data)
