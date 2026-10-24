from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .account_utils import user_has_als_email
from .models import UserProfile
from .models import AppSession


class BearerSessionAuthentication(BaseAuthentication):
    EMAIL_SETUP_ALLOWED_PATHS = {
        '/api/auth/me/',
        '/api/auth/me',
        '/api/auth/me/password/',
        '/api/auth/me/password',
        '/api/auth/logout/',
        '/api/auth/logout',
        '/api/auth/me/lab/',
        '/api/auth/me/lab',
        '/api/auth/labs/',
        '/api/auth/labs',
        '/api/auth/microsoft/status/',
        '/api/auth/microsoft/start/',
        '/api/auth/microsoft/callback/',
        '/api/auth/microsoft/disconnect/',
    }

    def authenticate(self, request):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return None
        token = header.removeprefix('Bearer ').strip()
        if not token:
            return None
        try:
            session = AppSession.objects.select_related('user').get(
                token_hash=AppSession.hash_token(token)
            )
        except AppSession.DoesNotExist:
            raise AuthenticationFailed('Invalid session token.')
        if not session.active:
            raise AuthenticationFailed('Session expired or revoked.')

        profile, _ = UserProfile.objects.get_or_create(user=session.user)
        is_admin = bool(session.user.is_superuser or profile.is_admin)
        if not is_admin and not profile.lab_id:
            raise PermissionDenied('An administrator must assign your lab before you can use the tracker.')
        if not profile.lab_id and not (
            request.path in self.EMAIL_SETUP_ALLOWED_PATHS or
            (is_admin and request.path.startswith('/api/auth/accounts/'))
        ):
            raise PermissionDenied('Choose your lab before using the tracker.')
        if not user_has_als_email(session.user) and request.path not in self.EMAIL_SETUP_ALLOWED_PATHS:
            # Allow an administrator to provision missing account details,
            # including their own, without weakening normal staff access.
            is_admin = bool(session.user.is_superuser or UserProfile.objects.filter(user=session.user, is_admin=True).exists())
            if not (is_admin and request.path.startswith('/api/auth/accounts/')):
                raise PermissionDenied('Ask an administrator to assign your ALS email address before continuing.')

        return (session.user, session)
