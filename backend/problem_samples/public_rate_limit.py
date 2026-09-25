"""Shared rate limits for the customer tracking API and file downloads."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone

from .models import PublicTrackingRateBucket


PUBLIC_PREFIXES = ('/api/public/problem-sample-tracking/', '/api/public/problem-acknowledgements/')


def _client_address(request):
    # Do not trust client-supplied forwarding headers unless the operator has
    # confirmed how many trusted proxies append to X-Forwarded-For.
    hops = getattr(settings, 'PUBLIC_TRACKING_TRUSTED_PROXY_HOPS', 0)
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if hops > 0 and forwarded:
        addresses = [value.strip() for value in forwarded.split(',')]
        if len(addresses) >= hops and addresses[-hops]:
            return addresses[-hops]
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _bucket_key(scope, subject, window, now):
    period = int(now.timestamp()) // window
    payload = f'public-tracking:{scope}:{subject}:{window}:{period}'.encode()
    key = hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    expires_at = datetime.fromtimestamp((period + 1) * window, tz=datetime_timezone.utc)
    return key, expires_at


def _take_slot(scope, subject, window, limit, now):
    key, expires_at = _bucket_key(scope, subject, window, now)
    PublicTrackingRateBucket.objects.get_or_create(key=key, defaults={'expires_at': expires_at})
    allowed = PublicTrackingRateBucket.objects.filter(key=key, count__lt=limit).update(count=F('count') + 1)
    return bool(allowed), max(1, int((expires_at - now).total_seconds()) + 1)


class PublicTrackingRateLimitMiddleware:
    """Bound token guessing and repeat actions using counters shared by workers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        prefix = next((p for p in PUBLIC_PREFIXES if request.path_info.startswith(p)), None)
        if prefix is None or request.method not in {'GET', 'HEAD', 'POST'}:
            return self.get_response(request)

        token = request.path_info[len(prefix):].split('/', 1)[0]
        address = _client_address(request)
        action = request.method == 'POST'
        if action:
            limits = (
                ('ip-write', address, 60, settings.PUBLIC_TRACKING_WRITE_LIMIT_PER_MINUTE),
                ('ip-write', address, 3600, settings.PUBLIC_TRACKING_WRITE_LIMIT_PER_HOUR),
                ('token-write', token, 60, 3),
                ('token-write', token, 3600, 12),
            )
        else:
            limits = (
                ('ip-read', address, 60, settings.PUBLIC_TRACKING_READ_LIMIT_PER_MINUTE),
                ('ip-read', address, 3600, settings.PUBLIC_TRACKING_READ_LIMIT_PER_HOUR),
                ('token-read', token, 60, 120),
            )
        now = timezone.now()
        for scope, subject, window, limit in limits:
            allowed, retry_after = _take_slot(scope, subject, window, limit, now)
            if not allowed:
                response = JsonResponse({'detail': 'Too many tracking requests. Please try again later.'}, status=429)
                response['Retry-After'] = str(retry_after)
                break
        else:
            response = self.get_response(request)
        response['Cache-Control'] = 'no-store'
        response['Referrer-Policy'] = 'no-referrer'
        # An occasional cleanup bounds the number of historical request rows.
        if secrets.randbelow(1000) == 0:
            PublicTrackingRateBucket.objects.filter(expires_at__lt=now - timedelta(hours=1)).delete()
        return response
