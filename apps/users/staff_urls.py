from django.urls import path

from . import views

urlpatterns = [
    path("staff/users", views.AdminUserListView.as_view(), name="staff-user-list"),
    path("staff/users/<uuid:pk>", views.AdminUserDetailView.as_view(), name="staff-user-detail"),
    path("staff/users/<uuid:pk>/block", views.AdminUserBlockView.as_view(), name="staff-user-block"),
    path("staff/users/<uuid:pk>/unblock", views.AdminUserUnblockView.as_view(), name="staff-user-unblock"),
]
