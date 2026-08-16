from django.urls import path

from . import views

urlpatterns = [
    path("staff/notices", views.AdminNoticeListCreateView.as_view(), name="staff-notice-list-create"),
    path("staff/notices/<uuid:pk>", views.AdminNoticeDetailView.as_view(), name="staff-notice-detail"),
]
