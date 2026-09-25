from rest_framework.permissions import BasePermission, SAFE_METHODS

from accounts.views import is_tracker_admin


class IsTrackerAdminOrReadOnly(BasePermission):
    """Staff can read table definitions; only admins can manage them."""

    message = 'Administrator access is required to manage tables.'

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_tracker_admin(request.user)
