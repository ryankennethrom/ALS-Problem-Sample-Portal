"""Monthly Distributor reporting: scopes, immutability, duplicate protection, and manual confirmation."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import ProblemColumn, ProblemSample, ProblemTable, SystemEmail
from .serializers import ProblemColumnSerializer
from .system_email_service import queue_due_monthly_reports


@override_settings(FRONTEND_URL='https://tracker.example.test')
class MonthlyDistributorReportTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Monthly table')
        self.other_table = ProblemTable.objects.create(name='Private table')
        self.column = ProblemColumn.objects.create(table=self.table, name='Distributor', field_key='distributor', column_type='distributor')
        self.other_column = ProblemColumn.objects.create(table=self.other_table, name='Distributor', field_key='distributor', column_type='distributor')
        self.user = User.objects.create_user(username='staff', email='staff@alsglobal.com')
        self.admin = User.objects.create_user(username='admin', email='admin@alsglobal.com')
        UserProfile.objects.create(user=self.admin, is_admin=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def configure(self, column=None, **kwargs):
        column = column or self.column
        rules = kwargs.get('rules', [
            {'match_type': 'wildcard', 'pattern': 'ACME*', 'cc_emails': ['one@example.com', 'ONE@example.com', 'two@example.com'], 'send_monthly_reports': True},
        ])
        serializer = ProblemColumnSerializer(column, data={'distributor_cc_rules': rules}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        column.refresh_from_db()
        return column.distributor_cc_rules

    def ticket(self, table, number, distributor, year, month, day, workflow='CS Follow-Up'):
        row = ProblemSample.objects.create(table=table, problem_number=number, current_workflow=workflow,
                                            custom_values={'distributor': distributor})
        created_at = timezone.make_aware(datetime(year, month, day, 12), ZoneInfo('America/Edmonton'))
        ProblemSample.objects.filter(pk=row.pk).update(created_at=created_at)
        return row

    def queue(self):
        return queue_due_monthly_reports(today=date(2026, 11, 1))

    def test_scopes_by_table_month_and_pattern_and_only_queues_once(self):
        self.configure()
        self.ticket(self.table, 10, 'Acme Transport', 2026, 10, 12, 'Back to testing')
        self.ticket(self.table, 11, 'Other', 2026, 10, 12)
        self.ticket(self.table, 12, 'ACME old', 2026, 9, 12)
        self.ticket(self.other_table, 13, 'ACME Private', 2026, 10, 12)
        self.ticket(self.table, 14, 'ACME November', 2026, 11, 1)
        result = self.queue()
        self.assertEqual(result['created'], 1)
        self.assertEqual(self.queue()['created'], 0)
        self.assertEqual(SystemEmail.objects.count(), 1)
        mail = SystemEmail.objects.get()
        self.assertEqual(mail.matched_ticket_count, 1)
        self.assertEqual(mail.to_emails, ['one@example.com', 'two@example.com'])
        self.assertIn('Back to testing: 1', mail.body)
        self.assertIn('Ticket #10', mail.body)
        for blocked in ['Ticket #11', 'Ticket #12', 'Ticket #13', 'Ticket #14']:
            self.assertNotIn(blocked, mail.body)
        self.assertEqual(mail.status, SystemEmail.STATUS_PENDING)

    def test_multiple_rules_generate_separate_emails_and_enabling_time_is_retained(self):
        rules = self.configure(rules=[
            {'match_type': 'contains', 'pattern': 'acme', 'cc_emails': ['a@example.com'], 'send_monthly_reports': True},
            {'match_type': 'contains', 'pattern': 'acme', 'cc_emails': ['b@example.com'], 'send_monthly_reports': True},
        ])
        original_ids = [r['id'] for r in rules]
        original_enabled = [r['monthly_reports_enabled_at'] for r in rules]
        self.configure(rules=rules[::-1])
        self.assertEqual([r['id'] for r in self.column.distributor_cc_rules], original_ids[::-1])
        self.assertEqual([r['monthly_reports_enabled_at'] for r in self.column.distributor_cc_rules], original_enabled[::-1])
        self.ticket(self.table, 20, 'ACME', 2026, 10, 11)
        self.assertEqual(self.queue()['created'], 2)
        self.assertEqual(self.queue()['created'], 0)
        self.assertEqual(set(tuple(e.to_emails) for e in SystemEmail.objects.all()), {('a@example.com',), ('b@example.com',)})

    def test_older_month_is_not_backfilled_by_newly_enabled_rule(self):
        self.configure()
        self.ticket(self.table, 32, 'ACME', 2026, 9, 11)
        self.assertEqual(queue_due_monthly_reports(today=date(2026, 10, 19))['created'], 0)

    def test_draft_requires_explicit_send_confirmation_and_rejects_duplicate(self):
        self.configure()
        self.ticket(self.table, 15, 'ACME', 2026, 10, 2)
        self.queue()
        message = SystemEmail.objects.get()
        listing = self.client.get('/api/system-emails/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['pending_count'], 1)
        self.assertNotIn('body', listing.data['emails'][0])
        detail = self.client.get(f'/api/system-emails/{message.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertIn('Ticket #15', detail.data['body'])
        self.assertEqual(self.client.post(f'/api/system-emails/{message.id}/confirm-sent/', {}, format='json').status_code, 400)
        message.refresh_from_db()
        self.assertEqual(message.status, SystemEmail.STATUS_PENDING)
        ok = self.client.post(f'/api/system-emails/{message.id}/confirm-sent/', {'confirmation': 'sent'}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.post(f'/api/system-emails/{message.id}/confirm-sent/', {'confirmation': 'sent'}, format='json').status_code, 409)
        self.assertEqual(self.client.get('/api/system-emails/').data['pending_count'], 0)
        message.refresh_from_db()
        self.assertEqual(message.sent_by, self.user)
        self.assertIsNotNone(message.sent_at)

    def test_manual_queue_requires_admin_and_anonymous_cannot_read(self):
        self.configure()
        self.assertEqual(self.client.post('/api/system-emails/queue-due/').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post('/api/system-emails/queue-due/').status_code, 200)
        anonymous = APIClient()
        self.assertIn(anonymous.get('/api/system-emails/').status_code, [401, 403])

    def test_rule_disabled_stops_future_months_but_does_not_change_pending_snapshot(self):
        rules = self.configure()
        self.ticket(self.table, 40, 'ACME', 2026, 10, 2)
        self.queue()
        previous_email = SystemEmail.objects.get()
        rules[0]['send_monthly_reports'] = False
        self.configure(rules=rules)
        self.assertEqual(queue_due_monthly_reports(today=date(2026, 12, 1))['created'], 0)
        previous_email.refresh_from_db()
        self.assertEqual(previous_email.status, SystemEmail.STATUS_PENDING)
