from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import AppSession

class BearerSessionAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header=request.headers.get('Authorization','')
        if not header.startswith('Bearer '):
            return None
        token=header.removeprefix('Bearer ').strip()
        if not token:
            return None
        try:
            session=(AppSession.objects.select_related('user')
                     .get(token_hash=AppSession.hash_token(token)))
        except AppSession.DoesNotExist:
            raise AuthenticationFailed('Invalid session token.')
        if not session.active:
            raise AuthenticationFailed('Session expired or revoked.')
        return (session.user, session)
