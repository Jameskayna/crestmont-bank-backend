from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditlog.utils import log_action
from apps.users.permissions import IsConfigManager, IsStaff

from .models import Notice, Notification
from .serializers import NoticeSerializer, NoticeWriteSerializer, NotificationSerializer


class NotificationListView(APIView):
    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        return Response(NotificationSerializer(notifications, many=True).data)


class NotificationMarkReadView(APIView):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"message": "All notifications marked as read."})


class ActiveNoticeListView(APIView):
    """Customer-facing: powers the dashboard banner. Any authenticated
    user, not just staff — this is a broadcast, not an admin surface."""

    def get(self, request):
        notices = Notice.objects.filter(is_active=True)
        return Response(NoticeSerializer(notices, many=True).data)


class AdminNoticeListCreateView(APIView):
    """Any staff can view; only admin/superadmin can create — same split
    as AdminLoanProductListCreateView."""

    permission_classes = [IsStaff]

    def get(self, request):
        notices = Notice.objects.all()
        return Response(NoticeSerializer(notices, many=True).data)

    def post(self, request):
        if not IsConfigManager().has_permission(request, self):
            return Response({"error": "Only admins can create notices."}, status=status.HTTP_403_FORBIDDEN)

        serializer = NoticeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notice = Notice.objects.create(created_by=request.user, **serializer.validated_data)
        log_action(request, "notice.create", "Notice", notice.id, metadata=serializer.validated_data)
        return Response(NoticeSerializer(notice).data, status=status.HTTP_201_CREATED)


class AdminNoticeDetailView(APIView):
    permission_classes = [IsStaff]

    def patch(self, request, pk):
        if not IsConfigManager().has_permission(request, self):
            return Response({"error": "Only admins can edit notices."}, status=status.HTTP_403_FORBIDDEN)

        notice = get_object_or_404(Notice, pk=pk)
        serializer = NoticeWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(notice, field, value)
        notice.save()
        log_action(request, "notice.update", "Notice", notice.id, metadata=serializer.validated_data)
        return Response(NoticeSerializer(notice).data)

    def delete(self, request, pk):
        if not IsConfigManager().has_permission(request, self):
            return Response({"error": "Only admins can delete notices."}, status=status.HTTP_403_FORBIDDEN)

        notice = get_object_or_404(Notice, pk=pk)
        log_action(request, "notice.delete", "Notice", notice.id)
        notice.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
