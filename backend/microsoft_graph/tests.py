"""Focused regression tests; run in WSL with a local PostgreSQL test DB."""
from unittest.mock import Mock, patch
import uuid

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import AppSession, Lab, UserProfile
from .models import MicrosoftMailConnection, MicrosoftMailSend
from .views import _addresses, _digest, _redirect_uri


class MicrosoftMailValidationTests(SimpleTestCase):
    def test_rejects_bad_addresses(self):
        with self.assertRaises(ValueError):
            _addresses(['bad-address'])
        with self.assertRaises(ValueError):
            _addresses('not a list')

    def test_deduplicates_cc_recipients(self):
        self.assertEqual(len(_addresses(['someone@example.org', 'SOMEONE@example.org'])), 1)

    @override_settings(FRONTEND_URL='https://tracker.example.test/')
    def test_registered_web_redirect_is_frontend_url(self):
        self.assertEqual(_redirect_uri(), 'https://tracker.example.test/auth/callback')


FERNET_KEY = Fernet.generate_key().decode()


@override_settings(
    MS_GRAPH_CLIENT_ID='11111111-1111-1111-1111-111111111111',
    MS_GRAPH_TENANT_ID='22222222-2222-2222-2222-222222222222',
    MS_GRAPH_CLIENT_SECRET='test-secret', MS_GRAPH_FERNET_KEY=FERNET_KEY,
    FRONTEND_URL='https://tracker.example.test',
)
class MicrosoftMailFlowTests(APITestCase):
    def setUp(self):
        self.lab = Lab.objects.create(name='Edmonton', code='EDM')
        self.user = User.objects.create_user(username='staff', password='temporary', email='staff@alsglobal.com')
        UserProfile.objects.create(user=self.user, role=UserProfile.ROLE_LAB_TECHNICIAN, lab=self.lab)
        token = AppSession.new_token()
        self.session = AppSession.objects.create(user=self.user, token_hash=AppSession.hash_token(token),
            expires_at=timezone.now() + __import__('datetime').timedelta(hours=1))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_optional_status_and_authorize_pkce(self):
        result = self.client.post('/api/auth/microsoft/start/')
        self.assertEqual(result.status_code, 200)
        self.assertIn('code_challenge_method=S256', result.data['authorization_url'])
        self.assertIn('https%3A%2F%2Ftracker.example.test%2Fauth%2Fcallback', result.data['authorization_url'])
        self.assertNotIn('test-secret', result.data['authorization_url'])

    def test_callback_requires_original_tracker_session(self):
        start = self.client.post('/api/auth/microsoft/start/')
        from urllib.parse import urlparse, parse_qs
        state = parse_qs(urlparse(start.data['authorization_url']).query)['state'][0]
        other_token = AppSession.new_token()
        AppSession.objects.create(user=self.user, token_hash=AppSession.hash_token(other_token),
            expires_at=timezone.now() + __import__('datetime').timedelta(hours=1))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        response = self.client.post('/api/auth/microsoft/callback/', {'state': state, 'code': '123'}, format='json')
        self.assertEqual(response.status_code, 400)

    @patch('microsoft_graph.views.requests.post')
    def test_graph_accepted_once_by_idempotency_key(self, post):
        blob = Fernet(FERNET_KEY.encode()).encrypt(__import__('json').dumps({
            'access_token': 'opaque', 'refresh_token': 'opaque-refresh',
        }).encode()).decode()
        MicrosoftMailConnection.objects.create(user=self.user, tenant_id='22222222-2222-2222-2222-222222222222',
            microsoft_user_id='oid', email=self.user.email, encrypted_tokens=blob,
            expires_at=timezone.now()+__import__('datetime').timedelta(hours=1))
        post.return_value = Mock(status_code=202)
        payload = dict(to=['customer@example.org'], cc=['cc@example.org'], subject='Status', body='Hello', idempotency_key=str(uuid.uuid4()))
        first = self.client.post('/api/auth/microsoft/send/', payload, format='json')
        second = self.client.post('/api/auth/microsoft/send/', payload, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(MicrosoftMailSend.objects.filter(status='accepted').count(), 1)
