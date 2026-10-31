"""Integration tests for administrator-controlled terminal tracking-link expiry."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT, PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_BACK_TO_TESTING,
    PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_TO_BE_DISPOSED,
    ProblemSample, ProblemTable, ProblemTrackingLink, generate_acknowledgement_token,
)


class TerminalTrackingExpiryTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Expiry policy table')
        self.sample = ProblemSample.objects.create(table=self.table, problem_number=1)
        self.link = ProblemTrackingLink.objects.create(
            ticket=self.sample, tracking_token=generate_acknowledgement_token(),
        )
        self.when = timezone.now().replace(microsecond=0)

    def change_workflow(self, workflow):
        old = self.sample.workflow_status
        self.sample.set_workflow_status(workflow)
        fields = self.sample.apply_acknowledgement_status_transition(
            old, previous_dispose_automatically=False, changed_at=self.when,
        )
        self.sample.save(update_fields=list(dict.fromkeys(['custom_values', 'current_workflow', *fields])))
        self.link.refresh_from_db()
        return self.link.expires_at

    def test_default_duration_preserves_thirty_days(self):
        self.assertEqual(self.table.terminal_tracking_link_days, 30)
        self.assertEqual(self.change_workflow(PROBLEM_STATUS_DISPOSED), self.when + timedelta(days=30))

    def test_custom_terminal_duration_applies_to_all_terminal_workflows(self):
        self.table.terminal_tracking_link_days = 14
        self.table.save(update_fields=['terminal_tracking_link_days'])
        for workflow in (PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_BACK_TO_TESTING, PROBLEM_STATUS_SHIPPED_BACK):
            with self.subTest(workflow=workflow):
                self.change_workflow(CURRENT_WORKFLOW_DEFAULT)
                self.assertEqual(self.change_workflow(workflow), self.when + timedelta(days=14))

    def test_never_expires_on_terminal(self):
        self.table.terminal_tracking_link_days = None
        self.table.save(update_fields=['terminal_tracking_link_days'])
        self.assertIsNone(self.change_workflow(PROBLEM_STATUS_DISPOSED))
        self.assertFalse(self.sample.tracking_link_expired)

    def test_zero_days_expires_immediately(self):
        self.table.terminal_tracking_link_days = 0
        self.table.save(update_fields=['terminal_tracking_link_days'])
        self.assertEqual(self.change_workflow(PROBLEM_STATUS_DISPOSED), self.when)

    def test_pending_workflow_keeps_old_thirty_day_window(self):
        self.table.terminal_tracking_link_days = None
        self.table.save(update_fields=['terminal_tracking_link_days'])
        self.assertEqual(self.change_workflow(PROBLEM_STATUS_TO_BE_DISPOSED), self.when + timedelta(days=30))
        self.assertIsNone(self.change_workflow(PROBLEM_STATUS_DISPOSED))

    def test_returning_to_followup_clears_expiration(self):
        self.change_workflow(PROBLEM_STATUS_DISPOSED)
        self.assertIsNone(self.change_workflow(CURRENT_WORKFLOW_DEFAULT))

    def test_changing_policy_does_not_reactivate_existing_links(self):
        self.change_workflow(PROBLEM_STATUS_DISPOSED)
        original = self.link.expires_at
        self.table.terminal_tracking_link_days = None
        self.table.save(update_fields=['terminal_tracking_link_days'])
        self.link.refresh_from_db()
        self.assertEqual(self.link.expires_at, original)


class TerminalTrackingExpiryAdminTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Admin policy table')
        self.admin = User.objects.create_superuser('expiry-admin', 'expiry-admin@example.org', 'p')
        self.staff = User.objects.create_user('expiry-staff')
        self.client = APIClient()
        self.url = f'/api/problem-tables/{self.table.pk}/'

    def test_admin_can_save_never_and_custom_day_count(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(self.url, {'terminal_tracking_link_days': None}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.table.refresh_from_db()
        self.assertIsNone(self.table.terminal_tracking_link_days)
        response = self.client.patch(self.url, {'terminal_tracking_link_days': 45}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.table.refresh_from_db()
        self.assertEqual(self.table.terminal_tracking_link_days, 45)

    def test_reject_out_of_range_days(self):
        self.client.force_authenticate(self.admin)
        for days in (-1, 3651):
            with self.subTest(days=days):
                response = self.client.patch(self.url, {'terminal_tracking_link_days': days}, format='json')
                self.assertEqual(response.status_code, 400, response.data)

    def test_staff_cannot_change_terminal_link_policy(self):
        self.client.force_authenticate(self.staff)
        response = self.client.patch(self.url, {'terminal_tracking_link_days': None}, format='json')
        self.assertEqual(response.status_code, 403)
        self.table.refresh_from_db()
        self.assertEqual(self.table.terminal_tracking_link_days, 30)
