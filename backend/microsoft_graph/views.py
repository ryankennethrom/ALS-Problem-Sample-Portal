"""Optional delegated Microsoft 365 email for existing tracker accounts.

IT registers a *Web* redirect URI at FRONTEND_URL/auth/callback, which forwards
its authorization code and state to this backend for server-side exchange.
PKCE and state are checked before linking any user. No Graph tokens reach JS.
"""
import base64
import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import jwt
import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.account_utils import user_has_als_email
from .models import MicrosoftAuthorizationAttempt, MicrosoftMailConnection, MicrosoftMailSend

GRAPH_SCOPES = 'openid profile email offline_access https://graph.microsoft.com/Mail.Send'
GRAPH_SEND_URL = 'https://graph.microsoft.com/v1.0/me/sendMail'


def _configured():
    return all([settings.MS_GRAPH_TENANT_ID, settings.MS_GRAPH_CLIENT_ID,
                settings.MS_GRAPH_CLIENT_SECRET, settings.MS_GRAPH_FERNET_KEY])


def _authority():
    return f'https://login.microsoftonline.com/{settings.MS_GRAPH_TENANT_ID}/oauth2/v2.0'


def _crypto():
    return Fernet(settings.MS_GRAPH_FERNET_KEY.encode('ascii'))


def _digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def _redirect_uri():
    # This exact Web redirect must be registered by IT. Never trust a client URL.
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/callback"


def _connection(user):
    return MicrosoftMailConnection.objects.filter(user=user).first()


def _expiry(seconds):
    return timezone.now() + timedelta(seconds=max(0, int(seconds) - 60))


def _authorization_error():
    return Response({'detail': 'Microsoft 365 mail is not yet configured by IT.'}, status=503)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def status_view(request):
    record = _connection(request.user)
    return Response({
        'configured': _configured(),
        'connected': bool(record and _configured()),
        'email': record.email if record and _configured() else '',
        'redirect_uri': _redirect_uri(),
        'mode': 'delegated',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_view(request):
    if not _configured():
        return _authorization_error()
    if not user_has_als_email(request.user):
        return Response({'detail': 'An administrator must assign your ALS email first.'}, status=403)
    # Only a tracker session may initiate a link; callback must bind to it.
    app_session = request.auth
    if not app_session or not getattr(app_session, 'active', False):
        return Response({'detail': 'Tracker session required.'}, status=401)
    MicrosoftAuthorizationAttempt.objects.filter(expires_at__lt=timezone.now()).delete()
    state = secrets.token_urlsafe(36)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    redirect_uri = _redirect_uri()
    MicrosoftAuthorizationAttempt.objects.create(
        state_hash=_digest(state), user=request.user, session=app_session,
        verifier=verifier, nonce=nonce, redirect_uri=redirect_uri,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    url = _authority() + '/authorize?' + urlencode({
        'client_id': settings.MS_GRAPH_CLIENT_ID,
        'response_type': 'code', 'redirect_uri': redirect_uri,
        'response_mode': 'query', 'scope': GRAPH_SCOPES,
        'state': state, 'nonce': nonce,
        'code_challenge': challenge, 'code_challenge_method': 'S256',
        'prompt': 'select_account',
        'login_hint': request.user.email,
    })
    return Response({'authorization_url': url})


def _verify_identity(id_token, attempt):
    # Validate the signature, issuer, audience, tenant, expiry AND nonce.
    jwks_url = f'https://login.microsoftonline.com/{settings.MS_GRAPH_TENANT_ID}/discovery/v2.0/keys'
    key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token, key, algorithms=['RS256'], audience=settings.MS_GRAPH_CLIENT_ID,
        issuer=f'https://login.microsoftonline.com/{settings.MS_GRAPH_TENANT_ID}/v2.0',
        options={'require': ['iss', 'aud', 'exp', 'iat', 'tid', 'oid', 'nonce']},
    )
    if claims['tid'].lower() != settings.MS_GRAPH_TENANT_ID.lower() or claims['nonce'] != attempt.nonce:
        raise ValueError('The Microsoft identity response did not match this request.')
    microsoft_email = str(claims.get('preferred_username') or claims.get('email') or '').strip().lower()
    tracker_email = str(attempt.user.email or '').strip().lower()
    if not microsoft_email or microsoft_email != tracker_email:
        raise ValueError('Your Microsoft 365 account must match the ALS email assigned by an administrator.')
    return claims['oid'], microsoft_email


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def callback_view(request):
    if not _configured():
        return _authorization_error()
    state = str(request.data.get('state') or '')
    code = str(request.data.get('code') or '')
    if not state or not code or len(state) > 256 or len(code) > 8192 or not state.isascii():
        return Response({'detail': 'Microsoft authorization was canceled or incomplete.'}, status=400)
    # Single-use state; consume BEFORE contacting the provider to avoid replay.
    with transaction.atomic():
        attempt = MicrosoftAuthorizationAttempt.objects.select_for_update().filter(state_hash=_digest(state)).first()
        if not attempt or attempt.expires_at <= timezone.now() or attempt.user_id != request.user.id or attempt.session_id != getattr(request.auth, 'id', None) or not attempt.session.active:
            return Response({'detail': 'Microsoft sign-in expired or does not match this tracker session. Try again.'}, status=400)
        attempt.delete()
    try:
        resp = requests.post(_authority() + '/token', data={
            'client_id': settings.MS_GRAPH_CLIENT_ID,
            'client_secret': settings.MS_GRAPH_CLIENT_SECRET,
            'grant_type': 'authorization_code', 'code': code,
            'redirect_uri': attempt.redirect_uri, 'code_verifier': attempt.verifier,
            'scope': GRAPH_SCOPES,
        }, timeout=15)
        data = resp.json()
        if resp.status_code != 200 or not data.get('access_token') or not data.get('refresh_token') or not data.get('id_token'):
            return Response({'detail': 'Microsoft did not authorize mail access. Check consent and application registration.'}, status=400)
        ms_id, email = _verify_identity(data['id_token'], attempt)
        enc = _crypto().encrypt(__import__('json').dumps({
            'access_token': data['access_token'], 'refresh_token': data['refresh_token'],
        }).encode()).decode('ascii')
        MicrosoftMailConnection.objects.update_or_create(user=request.user, defaults={
            'tenant_id': settings.MS_GRAPH_TENANT_ID,
            'microsoft_user_id': ms_id, 'email': email,
            'encrypted_tokens': enc, 'expires_at': _expiry(data.get('expires_in', 3600)),
        })
        return Response({'connected': True, 'email': email})
    except (requests.RequestException, ValueError, jwt.PyJWTError, InvalidToken, KeyError):
        # Never return provider tokens or auth codes to the browser/logs.
        return Response({'detail': 'Microsoft connection failed. Check that the signed-in Microsoft account matches your assigned ALS address and try again.'}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def disconnect_view(request):
    MicrosoftMailConnection.objects.filter(user=request.user).delete()
    return Response({'connected': False})


def _get_access_token(record):
    import json
    raw = json.loads(_crypto().decrypt(record.encrypted_tokens.encode('ascii')))
    if record.expires_at > timezone.now() and raw.get('access_token'):
        return raw['access_token']
    resp = requests.post(_authority() + '/token', data={
        'client_id': settings.MS_GRAPH_CLIENT_ID,
        'client_secret': settings.MS_GRAPH_CLIENT_SECRET,
        'grant_type': 'refresh_token', 'refresh_token': raw['refresh_token'],
        'scope': GRAPH_SCOPES,
    }, timeout=15)
    if resp.status_code != 200:
        raise ValueError('Microsoft session expired. Disconnect and reconnect your account.')
    data = resp.json()
    if not data.get('access_token'):
        raise ValueError('Microsoft mail permission is no longer available.')
    record.encrypted_tokens = _crypto().encrypt(json.dumps({
        'access_token': data['access_token'],
        'refresh_token': data.get('refresh_token') or raw['refresh_token'],
    }).encode()).decode('ascii')
    record.expires_at = _expiry(data.get('expires_in', 3600))
    record.save(update_fields=['encrypted_tokens', 'expires_at', 'updated_at'])
    return data['access_token']


def _addresses(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('Email recipients must be a list of up to 100 addresses.')
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    result, seen = [], set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError('Invalid email address.')
        address = item.strip()
        try:
            validate_email(address)
        except ValidationError:
            raise ValueError('Invalid recipient email address.') from None
        if address.lower() not in seen:
            seen.add(address.lower())
            result.append({'emailAddress': {'address': address}})
    return result


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_view(request):
    if not _configured():
        return _authorization_error()
    connection = _connection(request.user)
    if not connection:
        return Response({'detail': 'Connect Microsoft 365 in My Account before sending.'}, status=409)
    if connection.email.lower() != (request.user.email or '').strip().lower():
        return Response({'detail': 'Your assigned ALS email has changed. Disconnect and reconnect Microsoft 365.'}, status=403)
    try:
        to = _addresses(request.data.get('to', []))
        cc = _addresses(request.data.get('cc', []))
        subject = request.data.get('subject')
        body = request.data.get('body')
        if not to or not isinstance(subject, str) or not isinstance(body, str) or not subject.strip() or len(subject) > 300 or len(body) > 100_000:
            raise ValueError('A recipient, subject (up to 300 characters), and email body (up to 100,000 characters) are required.')
        key = uuid.UUID(str(request.data.get('idempotency_key')))
    except (ValueError, TypeError, AttributeError) as exc:
        return Response({'detail': str(exc)}, status=400)
    # Lock the delivery record across retries to prevent a second Graph send.
    with transaction.atomic():
        audit, _ = MicrosoftMailSend.objects.get_or_create(user=request.user, idempotency_key=key,
            defaults={'subject': subject[:300], 'recipient_count': len(to) + len(cc)})
        audit = MicrosoftMailSend.objects.select_for_update().get(pk=audit.pk)
        if audit.status == 'accepted':
            return Response({'status': 'accepted', 'message': 'Email already accepted by Microsoft.'})
        if audit.status == 'attempted':
            return Response({'detail': 'This email may already have been submitted. Verify Sent Items before retrying.'}, status=409)
        # Mark attempted first; network failure may be ambiguous. Don't blindly retry.
        audit.status = 'attempted'
        audit.save(update_fields=['status'])
    try:
        access_token = _get_access_token(connection)
        response = requests.post(GRAPH_SEND_URL, json={'message': {
            'subject': subject, 'body': {'contentType': 'Text', 'content': body},
            'toRecipients': to, 'ccRecipients': cc,
        }, 'saveToSentItems': True}, headers={
            'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json',
        }, timeout=20)
    except (requests.RequestException, InvalidToken, ValueError, KeyError):
        return Response({'detail': 'Email Not Sent (or confirmation unavailable). Check Outlook Sent Items before retrying.'}, status=502)
    if response.status_code != 202:
        # Explicit HTTP rejection means no acceptance; permit a fresh user action/key.
        audit.status = 'rejected'
        audit.save(update_fields=['status'])
        return Response({'detail': 'Email Not Sent. Microsoft Graph rejected the request. Verify your Microsoft 365 connection and permissions.'}, status=502)
    audit.status = 'accepted'
    audit.accepted_at = timezone.now()
    audit.save(update_fields=['status', 'accepted_at'])
    return Response({'status': 'accepted', 'message': 'Email Sent — accepted by Microsoft 365 (delivery is not yet guaranteed).'})
