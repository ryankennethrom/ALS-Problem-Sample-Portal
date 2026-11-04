"""Django integration tests for automatic disposal changes at priority escalation.

Run: python manage.py test problem_samples.client_email_escalation_disposal_tests
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .client_email_escalation import try_escalate_ticket
from .models import ProblemColumn, ProblemHistory, ProblemSample, ProblemTable


class ClientEmailEscalationDisposalIntegrationTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Escalation disables disposal')
        self.end_user = ProblemColumn.objects.create(
            table=self.table, name='End User', field_key='end-user',
            column_type=ProblemColumn.TYPE_END_USER,
        )
        self.distributor = ProblemColumn.objects.create(
            table=self.table, name='Distributor', field_key='distributor',
            column_type=ProblemColumn.TYPE_DISTRIBUTOR,
        )
        self.email_column = ProblemColumn.objects.create(
            table=self.table, name='Client Contact Email', field_key='client-contact-email',
            column_type=ProblemColumn.TYPE_CLIENT_EMAIL,
            client_email_fallback_hours=1,
            client_email_dependencies=[str(self.end_user.pk), str(self.distributor.pk)],
        )
        self.ticket = ProblemSample.objects.create(
            table=self.table, problem_number=1,
            current_workflow='Waiting for Customer Response',
            custom_values={
                'current-workflow': 'Waiting for Customer Response',
                'dispose-automatically': 'Yes',
                'end-user': 'End Co',
                'distributor': 'Dist Co',
                'client-contact-email': ['end@example.com'],
            },
            client_email_priority_state={str(self.email_column.pk): 0},
            client_email_last_tracking_sent_at=timezone.now() - timedelta(hours=2),
            automatic_disposal_started_at=timezone.now() - timedelta(days=1),
        )

    @patch('problem_samples.client_email_escalation._emails_for_company')
    def test_escalation_disables_disposal_and_countdown_in_saved_ticket(self, emails):
        emails.side_effect = lambda company: ['dist@example.com'] if company == 'Dist Co' else ['end@example.com']
        self.assertTrue(try_escalate_ticket(self.ticket, now=timezone.now()))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, 'Follow Up Required')
        self.assertFalse(self.ticket.dispose_automatically)
        self.assertEqual(self.ticket.custom_values['dispose-automatically'], 'No')
        self.assertIsNone(self.ticket.expires_at)
        event = ProblemHistory.objects.filter(problem=self.ticket).first()
        self.assertIn({'field': 'Dispose Automatically', 'before': 'Yes', 'after': 'No'}, event.details['changes'])

    @patch('problem_samples.client_email_escalation._emails_for_company')
    def test_too_early_does_not_turn_off_disposal(self, emails):
        emails.return_value = ['dist@example.com']
        self.ticket.client_email_last_tracking_sent_at = timezone.now()
        self.ticket.save(update_fields=['client_email_last_tracking_sent_at'])
        self.assertFalse(try_escalate_ticket(self.ticket, now=timezone.now()))
        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.dispose_automatically)
        self.assertIsNotNone(self.ticket.expires_at)
        self.assertFalse(ProblemHistory.objects.filter(problem=self.ticket).exists())
