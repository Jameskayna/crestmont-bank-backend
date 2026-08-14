from rest_framework.permissions import BasePermission

STAFF_ROLES = {"support", "compliance", "admin", "superadmin"}
APPROVER_ROLES = {"compliance", "admin", "superadmin"}
CONFIG_ROLES = {"admin", "superadmin"}


class IsStaff(BasePermission):
    """Any staff role: read access to users/accounts/loans, KYC review.
    Matches the support role's stated capability — view accounts, verify
    KYC, cannot move money."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in STAFF_ROLES)


class IsApprover(BasePermission):
    """Compliance and above: actions that move money, freeze accounts, or
    decide loans/withdrawals. Support is deliberately excluded."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in APPROVER_ROLES)


class IsConfigManager(BasePermission):
    """Admin/superadmin only: loan product rate and term configuration."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in CONFIG_ROLES)
