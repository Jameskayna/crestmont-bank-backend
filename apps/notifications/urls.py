from django.urls import path

from . import views

urlpatterns = [
    path("notifications", views.NotificationListView.as_view(), name="notification-list"),
    path("notifications/read-all", views.NotificationMarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("notifications/<uuid:pk>/read", views.NotificationMarkReadView.as_view(), name="notification-mark-read"),
    path("notices/active", views.ActiveNoticeListView.as_view(), name="notice-active-list"),
]
