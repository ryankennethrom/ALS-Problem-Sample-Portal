import base64

from django.contrib.auth.models import User
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT, PROBLEM_STATUS_TO_BE_DISPOSED, SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    ProblemSample, ProblemTrackingLink, ProblemTable, generate_acknowledgement_token,
)


class TrackingTokenTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='security.staff')
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff)
        self.table = ProblemTable.objects.create(name='Security table', is_default=True)
        self.sample = ProblemSample.objects.create(table=self.table, problem_number=1)

    def test_generated_tokens_have_384_bits_of_random_input(self):
        tokens = [generate_acknowledgement_token() for _ in range(10)]
        self.assertEqual(len(set(tokens)), len(tokens))
        for token in tokens:
            self.assertEqual(len(token), 64)
            self.assertEqual(len(base64.urlsafe_b64decode(token)), 48)

    def test_only_server_issued_pending_token_can_be_confirmed(self):
        endpoint = f'/api/problem-samples/{self.sample.pk}/'
        prepared = self.staff_client.post(endpoint + 'customer-notification-credentials/')
        self.assertEqual(prepared.status_code, 200)
        token = prepared.data['tracking_token']
        self.sample.refresh_from_db()
        self.assertIsNone(self.sample.acknowledgement_token)
        self.assertEqual(self.sample.pending_tracking_token, token)
        forged = self.staff_client.post(endpoint + 'customer-notification-sent/', {
            'tracking_token': generate_acknowledgement_token(), 'delivery_method': 'mailto',
        }, format='json')
        self.assertEqual(forged.status_code, 409)
        self.sample.refresh_from_db()
        self.assertIsNone(self.sample.acknowledgement_token)
        confirmed = self.staff_client.post(endpoint + 'customer-notification-sent/', {
            'tracking_token': token, 'delivery_method': 'mailto',
        }, format='json')
        self.assertEqual(confirmed.status_code, 201, confirmed.data)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.acknowledgement_token, token)
        self.assertIsNone(self.sample.pending_tracking_token)


class PublicTrackingRateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token = generate_acknowledgement_token()
        self.path = f'/api/public/problem-sample-tracking/{self.token}/'
        self.legacy_path = f'/api/public/problem-acknowledgements/{self.token}/'

    @override_settings(PUBLIC_TRACKING_READ_LIMIT_PER_MINUTE=2)
    def test_read_limits_shared_across_legacy_alias_and_ignore_untrusted_forwarded_ip(self):
        self.assertEqual(self.client.get(self.path, REMOTE_ADDR='198.51.100.1').status_code, 404)
        self.assertEqual(self.client.get(self.legacy_path, REMOTE_ADDR='198.51.100.1', HTTP_X_FORWARDED_FOR='203.0.113.1').status_code, 404)
        limited = self.client.get(self.path, REMOTE_ADDR='198.51.100.1', HTTP_X_FORWARDED_FOR='203.0.113.2')
        self.assertEqual(limited.status_code, 429)
        self.assertIn('Retry-After', limited)
        self.assertEqual(limited['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get(self.path, REMOTE_ADDR='198.51.100.2').status_code, 404)

    @override_settings(PUBLIC_TRACKING_WRITE_LIMIT_PER_MINUTE=2)
    def test_write_limit_includes_invalid_tokens_and_is_separate_from_reads(self):
        self.assertEqual(self.client.post(self.path, {'action': 'dispose'}, format='json').status_code, 404)
        self.assertEqual(self.client.post(self.legacy_path, {'action': 'dispose'}, format='json').status_code, 404)
        self.assertEqual(self.client.post(self.path, {'action': 'dispose'}, format='json').status_code, 429)
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_short_legacy_token_is_not_accepted(self):
        table = ProblemTable.objects.create(name='Legacy token test')
        sample = ProblemSample.objects.create(table=table, problem_number=1)
        ProblemTrackingLink.objects.create(ticket=sample, tracking_token='short-token')
        self.assertEqual(self.client.get('/api/public/problem-sample-tracking/short-token/').status_code, 404)

    def test_per_token_write_limit_cannot_be_bypassed_by_changing_address(self):
        for offset in range(3):
            response = self.client.post(self.path, {'action': 'dispose'}, format='json', REMOTE_ADDR=f'198.51.100.{offset + 1}')
            self.assertEqual(response.status_code, 404)
        blocked = self.client.post(self.legacy_path, {'action': 'dispose'}, format='json', REMOTE_ADDR='198.51.100.4')
        self.assertEqual(blocked.status_code, 429)

    @override_settings(PUBLIC_TRACKING_READ_LIMIT_PER_MINUTE=1)
    def test_file_downloads_share_public_read_budget(self):
        self.assertEqual(self.client.get(self.path + 'images/1234/').status_code, 404)
        self.assertEqual(self.client.get(self.path).status_code, 429)


class ProblemTrackingLinkTableTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Tracking link table test')

    def _sample(self, number):
        return ProblemSample.objects.create(
            table=self.table, problem_number=number, current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT},
        )

    def test_token_is_unique_and_ticket_has_at_most_one_tracking_row(self):
        first = self._sample(1)
        second = self._sample(2)
        token = generate_acknowledgement_token()
        ProblemTrackingLink.objects.create(ticket=first, tracking_token=token)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProblemTrackingLink.objects.create(ticket=second, tracking_token=token)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProblemTrackingLink.objects.create(ticket=first, tracking_token=generate_acknowledgement_token())

    def test_deleting_ticket_cascades_to_tracking_link(self):
        sample = self._sample(1)
        link = ProblemTrackingLink.objects.create(ticket=sample, tracking_token=generate_acknowledgement_token())
        link_id = link.pk
        sample.delete()
        self.assertFalse(ProblemTrackingLink.objects.filter(pk=link_id).exists())

    def test_workflow_expiration_is_persisted_on_tracking_link(self):
        sample = self._sample(1)
        link = ProblemTrackingLink.objects.create(ticket=sample, tracking_token=generate_acknowledgement_token())
        changed_at = timezone.now()
        sample.set_workflow_status(PROBLEM_STATUS_TO_BE_DISPOSED)
        fields = sample.apply_acknowledgement_status_transition(
            CURRENT_WORKFLOW_DEFAULT, previous_dispose_automatically=False, changed_at=changed_at,
        )
        sample.save(update_fields=list(dict.fromkeys(['custom_values', 'current_workflow', *fields])))
        link.refresh_from_db()
        self.assertEqual(link.expires_at, changed_at + timedelta(days=30))
