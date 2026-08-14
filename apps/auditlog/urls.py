from django.urls import path

from . import views

urlpatterns = [
    path("staff/audit-log", views.AuditLogListView.as_view(), name="staff-audit-log"),
]
