from rest_framework.permissions import BasePermission

from accounts.models import UserProfile


class IsTrackerAdmin(BasePermission):
    """Allow access only to tracker administrators or Django superusers."""

    message = 'Administrator access is required.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return bool(profile.is_admin)
