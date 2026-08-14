from django.urls import path

from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("read-all", views.NotificationMarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("<uuid:pk>/read", views.NotificationMarkReadView.as_view(), name="notification-mark-read"),
]
