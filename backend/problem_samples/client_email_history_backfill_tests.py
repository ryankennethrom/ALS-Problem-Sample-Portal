"""Django integration checks for the 0102 historical-priority backfill.

Run: python manage.py test problem_samples.client_email_history_backfill_tests
"""
from datetime import timedelta
from types import SimpleNamespace

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from .models import ProblemHistory, ProblemSample, ProblemTable
import importlib

migration = importlib.import_module('problem_samples.migrations.0102_backfill_client_email_priority_history')


class ClientEmailHistoryBackfillTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='History backfill test')
        self.start = timezone.now() - timedelta(days=12)
        self.schema_editor = SimpleNamespace(connection=SimpleNamespace(alias='default'))

    def ticket(self, number):
        return ProblemSample.objects.create(table=self.table, problem_number=number,
            current_workflow='Waiting for Customer Response')

    def event(self, ticket, action, summary, at, details=None):
        record = ProblemHistory.objects.create(problem=ticket, action=action,
            summary=summary, details=details or {})
        ProblemHistory.objects.filter(pk=record.pk).update(created_at=at)
        return record

    def run_migration(self):
        migration.backfill_from_history(apps, self.schema_editor)

    def test_legacy_send_is_used_and_newest_send_wins(self):
        ticket = self.ticket(101)
        self.event(ticket, 'customer_notification', 'Sent tracking link to customer by email', self.start)
        latest = self.start + timedelta(days=3)
        self.event(ticket, 'customer_notification', 'Sent tracking link to customer by email', latest)
        self.run_migration()
        ticket.refresh_from_db()
        self.assertEqual(ticket.client_email_last_tracking_sent_at, latest)
        self.assertIsNone(ticket.client_email_last_customer_response_at)

    def test_only_real_confirmed_tracking_sends_count(self):
        ticket = self.ticket(102)
        self.event(ticket, 'updated', 'Customer tracking email not sent', self.start)
        self.event(ticket, 'customer_notification', 'Sent an email to the customer', self.start)
        self.run_migration()
        ticket.refresh_from_db()
        self.assertIsNone(ticket.client_email_last_tracking_sent_at)

    def test_acknowledgement_and_later_public_response_are_counted(self):
        ticket = self.ticket(103)
        self.event(ticket, 'customer_notification', 'Sent tracking link to customer by email', self.start)
        ack = self.start + timedelta(hours=1)
        last = self.start + timedelta(days=2)
        self.event(ticket, 'acknowledged', 'Customer acknowledged ticket', ack)
        self.event(ticket, 'updated', 'Customer selected: Message us about the issue', last,
                   {'responded_via': 'public_tracking_link'})
        self.run_migration()
        ticket.refresh_from_db()
        self.assertEqual(ticket.client_email_last_customer_response_at, last)

    def test_existing_newer_timestamps_not_overwritten(self):
        ticket = self.ticket(104)
        newer = timezone.now() - timedelta(hours=1)
        ticket.client_email_last_tracking_sent_at = newer
        ticket.save(update_fields=['client_email_last_tracking_sent_at'])
        self.event(ticket, 'customer_notification', 'Sent tracking link to customer by email', self.start)
        self.run_migration()
        ticket.refresh_from_db()
        self.assertEqual(ticket.client_email_last_tracking_sent_at, newer)

    def test_repeated_run_is_idempotent_and_preserves_workflow(self):
        ticket = self.ticket(105)
        self.event(ticket, 'customer_notification', 'Sent tracking link to customer by email', self.start)
        self.run_migration()
        self.run_migration()
        ticket.refresh_from_db()
        self.assertEqual(ticket.client_email_last_tracking_sent_at, self.start)
        self.assertEqual(ticket.current_workflow, 'Waiting for Customer Response')
        self.assertEqual(ticket.history.count(), 1)  # migration must not generate activity
