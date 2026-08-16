from django.urls import path

from . import views

urlpatterns = [
    path("staff/cards", views.AdminCardListView.as_view(), name="staff-card-list"),
    path("staff/cards/<uuid:pk>/block", views.AdminCardBlockView.as_view(), name="staff-card-block"),
    path("staff/cards/<uuid:pk>/reactivate", views.AdminCardReactivateView.as_view(), name="staff-card-reactivate"),
    path("staff/accounts/<uuid:pk>/freeze", views.AdminAccountFreezeView.as_view(), name="staff-account-freeze"),
    path("staff/accounts/<uuid:pk>/unfreeze", views.AdminAccountUnfreezeView.as_view(), name="staff-account-unfreeze"),
    path("staff/adjustments", views.AdminAdjustmentListCreateView.as_view(), name="staff-adjustment-list-create"),
    path(
        "staff/adjustments/<uuid:pk>/approve",
        views.AdminAdjustmentApproveView.as_view(),
        name="staff-adjustment-approve",
    ),
    path(
        "staff/adjustments/<uuid:pk>/reject",
        views.AdminAdjustmentRejectView.as_view(),
        name="staff-adjustment-reject",
    ),
    path("staff/withdrawals", views.AdminWithdrawalListView.as_view(), name="staff-withdrawal-list"),
    path(
        "staff/withdrawals/<uuid:pk>/approve",
        views.AdminWithdrawalApproveView.as_view(),
        name="staff-withdrawal-approve",
    ),
    path(
        "staff/withdrawals/<uuid:pk>/reject",
        views.AdminWithdrawalRejectView.as_view(),
        name="staff-withdrawal-reject",
    ),
]
