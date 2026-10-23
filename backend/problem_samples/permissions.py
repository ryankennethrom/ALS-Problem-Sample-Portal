from rest_framework.permissions import BasePermission, SAFE_METHODS

from accounts.views import is_tracker_admin
from .labs import active_lab


class IsTrackerAdminOrReadOnly(BasePermission):
    """Staff can read table definitions; only admins can manage them."""

    message = 'Administrator access is required to manage tables.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return is_tracker_admin(request.user) and active_lab(request) is None
