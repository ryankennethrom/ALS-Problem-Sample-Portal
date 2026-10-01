from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER, PROBLEM_STATUS_SHIPPED_BACK, ProblemHistory, ProblemSample, ProblemTrackingLink)
from .views import get_default_table


class TrackingLinkControlsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='tracking.controls')
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.ticket = ProblemSample.objects.create(table=get_default_table(), problem_number=1)
        self.ticket.table.next_problem_id = 2
        self.ticket.table.save(update_fields=['next_problem_id'])
        self.base = f'/api/problem-samples/{self.ticket.pk}/'
        self.public = APIClient()

    def prepare(self):
        result = self.client.post(self.base + 'customer-notification-credentials/')
        self.assertEqual(result.status_code, 200, result.data)
        return result.data['tracking_token']

    def send(self, token):
        result = self.client.post(self.base + 'customer-notification-sent/', {
            'tracking_token': token, 'delivery_method': 'mailto',
        }, format='json')
        self.assertEqual(result.status_code, 201, result.data)

    def test_sent_tracking_link_moves_cs_follow_up_to_waiting_for_customer_response(self):
        token = self.prepare()
        self.send(token)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)
        history = self.ticket.history.get(summary='Sent tracking link to customer by email')
        self.assertIn({
            'field': 'Current Workflow',
            'before': CURRENT_WORKFLOW_DEFAULT,
            'after': CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
        }, history.details['changes'])

    def test_sent_tracking_link_does_not_override_terminal_workflow(self):
        self.ticket.set_workflow_status(PROBLEM_STATUS_SHIPPED_BACK)
        self.ticket.save(update_fields=['current_workflow', 'custom_values'])
        token = self.prepare()
        self.send(token)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, PROBLEM_STATUS_SHIPPED_BACK)

    def test_direct_create_requires_tracking_email_preparation(self):
        created = self.client.post('/api/problem-samples/', {
            'table': str(self.ticket.table_id), 'custom_values': {},
        }, format='json')
        self.assertEqual(created.status_code, 409, created.data)
        self.assertEqual(ProblemSample.objects.count(), 1)
        self.assertFalse(ProblemTrackingLink.objects.exists())

    def test_general_email_does_not_create_link_or_start_automatic_disposal(self):
        result = self.client.post(self.base + 'customer-message-sent/', {
            'to': ['customer@example.com'], 'subject': 'Regarding your sample',
            'body': 'We are reviewing the issue.',
        }, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.ticket.refresh_from_db()
        self.assertFalse(ProblemTrackingLink.objects.filter(ticket=self.ticket).exists())
        self.assertIsNone(self.ticket.pending_tracking_token)
        self.assertIsNone(self.ticket.customer_notified_at)
        self.assertFalse(self.ticket.dispose_automatically)
        self.assertTrue(self.ticket.history.filter(summary='Sent an email to the customer').exists())
        self.assertEqual(self.client.post(self.base + 'customer-message-sent/', {
            'to': ['invalid'], 'subject': 'Hi', 'body': 'Hello',
        }, format='json').status_code, 400)

    def test_general_email_leaves_existing_tracking_link_and_countdown_unchanged(self):
        token = self.prepare()
        self.send(token)
        self.ticket.refresh_from_db()
        before = (self.ticket.customer_notified_at, self.ticket.automatic_disposal_started_at,
                  self.ticket.dispose_automatically)
        response = self.client.post(self.base + 'customer-message-sent/', {
            'to': ['customer@example.com'], 'subject': 'Additional information', 'body': 'Please call us.',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.customer_notified_at, self.ticket.automatic_disposal_started_at,
                          self.ticket.dispose_automatically), before)
        self.assertEqual(self.ticket.acknowledgement_token, token)

    def test_revocation_invalidates_old_link_and_new_send_uses_fresh_token(self):
        first = self.prepare()
        self.send(first)
        self.ticket.refresh_from_db()
        first_notified_at = self.ticket.customer_notified_at
        self.assertEqual(self.public.get(f'/api/public/problem-sample-tracking/{first}/').status_code, 200)

        revoked = self.client.post(self.base + 'revoke-tracking-link/', {}, format='json', HTTP_X_CHANGE_REASON='Sent to wrong address')
        self.assertEqual(revoked.status_code, 200, revoked.data)
        self.assertEqual(self.public.get(f'/api/public/problem-sample-tracking/{first}/').status_code, 404)
        self.assertEqual(self.public.post(f'/api/public/problem-sample-tracking/{first}/', {'action': 'hold'}, format='json').status_code, 404)
        self.assertIsNone(self.client.get(self.base).data['tracking_url'] or None)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertGreaterEqual(self.client.get('/api/dashboard/').data['counts']['tracking_not_sent'], 1)
        self.assertTrue(ProblemHistory.objects.filter(problem=self.ticket, summary='Revoked tracking link', details__reason='Sent to wrong address').exists())
        self.assertEqual(self.client.post(self.base + 'revoke-tracking-link/', {}).status_code, 409)

        second = self.prepare()
        self.assertNotEqual(first, second)
        self.assertEqual(self.client.post(self.base + 'customer-notification-sent/', {
            'tracking_token': first, 'delivery_method': 'mailto',
        }, format='json').status_code, 409)
        self.send(second)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.customer_notified_at, first_notified_at)
        self.assertEqual(self.public.get(f'/api/public/problem-sample-tracking/{first}/').status_code, 404)
        self.assertEqual(self.public.get(f'/api/public/problem-sample-tracking/{second}/').status_code, 200)
        self.assertEqual(self.ticket.history.filter(summary='Sent tracking link to customer by email').count(), 2)

    def test_revoking_clears_other_pending_credentials(self):
        token = self.prepare()
        self.send(token)
        self.ticket.pending_tracking_token = 'x' * 64
        self.ticket.save(update_fields=['pending_tracking_token'])
        self.assertEqual(self.client.post(self.base + 'revoke-tracking-link/', {}).status_code, 200)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.pending_tracking_token)
