from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .account_utils import user_has_als_email
from .models import AppSession


class BearerSessionAuthentication(BaseAuthentication):
    EMAIL_SETUP_ALLOWED_PATHS = {
        '/api/auth/me/',
        '/api/auth/me',
        '/api/auth/logout/',
        '/api/auth/logout',
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

        if not user_has_als_email(session.user) and request.path not in self.EMAIL_SETUP_ALLOWED_PATHS:
            raise PermissionDenied('Set your ALS email address before continuing.')

        return (session.user, session)
