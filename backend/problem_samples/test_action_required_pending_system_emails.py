"""Django integration tests for pending system mail in Action Required digests."""
from datetime import date
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Lab, UserProfile
from .dashboard_views import action_required_snapshot
from .models import ProblemColumn, ProblemTable, SystemEmail


@override_settings(FRONTEND_URL='https://tracker.example.test')
class PendingSystemEmailDigestTests(TestCase):
    def setUp(self):
        self.edmonton = Lab.objects.create(name='Edmonton', code='EDM')
        self.calgary = Lab.objects.create(name='Calgary', code='YYC')
        self.user = User.objects.create_user(username='sender', email='sender@alsglobal.com')
        UserProfile.objects.create(user=self.user, is_admin=True, lab=self.edmonton)
        table = ProblemTable.objects.create(name='Brand reporting')
        self.column = ProblemColumn.objects.create(
            table=table, name='Brand', field_key='brand', column_type=ProblemColumn.TYPE_BRAND,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_email(self, lab, status=SystemEmail.STATUS_PENDING):
        return SystemEmail.objects.create(
            source_column=self.column, rule_identifier=uuid4(), lab=lab,
            period_start=date(2026, 10, 1), period_end=date(2026, 11, 1),
            distributor_pattern='northstar', to_emails=['recipient@example.test'],
            subject='Monthly Brand Report', body='Monthly Brand Report', status=status,
        )

    def test_snapshot_counts_pending_emails_by_lab_and_all_labs(self):
        self.create_email(self.edmonton)
        self.create_email(self.edmonton)
        self.create_email(self.calgary)
        self.create_email(self.edmonton, status=SystemEmail.STATUS_SENT)
        self.assertEqual(action_required_snapshot(lab=self.edmonton)['pending_system_emails'], 2)
        self.assertEqual(action_required_snapshot(lab=self.calgary)['pending_system_emails'], 1)
        self.assertEqual(action_required_snapshot()['pending_system_emails'], 3)

    def test_email_draft_contains_pending_count_and_correct_link_and_refreshes(self):
        first = self.create_email(self.edmonton)
        self.create_email(self.calgary)
        self.client.credentials(HTTP_X_ACTIVE_LAB='EDM')
        response = self.client.post('/api/dashboard/action-required-email/', {
            'recipients': ['@sender'], 'message': '',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['counts']['pending_system_emails'], 1)
        self.assertIn('- Pending System Emails: 1', response.data['body'])
        self.assertIn('https://tracker.example.test/send-system-emails#pending-system-emails', response.data['body'])

        first.status = SystemEmail.STATUS_SENT
        first.save(update_fields=['status'])
        refreshed = self.client.post('/api/dashboard/action-required-email/', {
            'recipients': ['@sender'],
        }, format='json')
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.assertEqual(refreshed.data['counts']['pending_system_emails'], 0)
        self.assertIn('- Pending System Emails: 0', refreshed.data['body'])
