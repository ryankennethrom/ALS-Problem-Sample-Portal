from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT,
    CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
    ProblemColumn,
    ProblemHistory,
    ProblemSample,
    ProblemTable,
    ProblemTrackingLink,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    generate_acknowledgement_token,
)


@override_settings(FRONTEND_URL='https://tracker.example')
class CustomerHistoryReplyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='staff.reply', email='staff.reply@alsglobal.com')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = ProblemTable.objects.create(name='Tickets', is_default=True)
        self.email_column = ProblemColumn.objects.create(
            table=self.table,
            name='Client Email',
            field_key='client-email',
            column_type=ProblemColumn.TYPE_CLIENT_EMAIL,
            position=1,
        )
        self.problem = ProblemSample.objects.create(
            table=self.table,
            problem_number=1,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={
                SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                'client-email': ['customer@example.com', 'second@example.com'],
            },
        )
        self.link = ProblemTrackingLink.objects.create(
            ticket=self.problem,
            tracking_token=generate_acknowledgement_token(),
        )
        self.customer_history = ProblemHistory.objects.create(
            problem=self.problem,
            action=ProblemHistory.ACTION_UPDATED,
            summary='Customer selected: Message us about the issue',
            details={
                'responded_via': 'public_tracking_link',
                'customer_requested_information': 'The bottle arrived damaged.',
                'customer_signature': 'Customer Name',
            },
        )

    def test_prepare_reply_contains_original_message_staff_reply_and_direct_modal_link(self):
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {'history_id': self.customer_history.pk, 'reply': 'Please send us a replacement photo.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        email = response.data['email']
        self.assertEqual(email['to'], ['customer@example.com', 'second@example.com'])
        self.assertIn('The bottle arrived damaged.', email['body'])
        self.assertIn('Please send us a replacement photo.', email['body'])
        self.assertIn('ensure swift correspondence', email['body'])
        self.assertEqual(
            email['direct_url'],
            f'https://tracker.example/track/{self.link.tracking_token}?message=1',
        )
        self.assertIn(email['direct_url'], email['body'])
        self.assertTrue(response.data['confirmation_token'])

    def test_reply_is_not_saved_without_email_confirmation(self):
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {'history_id': self.customer_history.pk, 'reply': 'Staff response'},
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ProblemHistory.objects.filter(problem=self.problem, summary='Replied to customer message').exists())

    def test_confirmed_reply_is_saved_and_moves_cs_follow_up_to_waiting(self):
        reply = 'Please use the link to send another photo.'
        prepared = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {'history_id': self.customer_history.pk, 'reply': reply},
            format='json',
        )
        self.assertEqual(prepared.status_code, 200, prepared.data)
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {
                'history_id': self.customer_history.pk,
                'reply': reply,
                'confirmation_token': prepared.data['confirmation_token'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)
        history = ProblemHistory.objects.get(problem=self.problem, summary='Replied to customer message')
        self.assertEqual(history.actor, self.user)
        self.assertEqual(history.details['replied_to_history_id'], self.customer_history.pk)
        self.assertEqual(history.details['customer_message'], 'The bottle arrived damaged.')
        self.assertEqual(history.details['staff_reply'], reply)
        self.assertEqual(history.details['recipients'], ['customer@example.com', 'second@example.com'])
        self.assertEqual(history.details['changes'][0]['field'], 'Current Workflow')

    def test_changed_reply_invalidates_confirmation(self):
        prepared = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {'history_id': self.customer_history.pk, 'reply': 'First reply'},
            format='json',
        )
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {
                'history_id': self.customer_history.pk,
                'reply': 'Changed reply',
                'confirmation_token': prepared.data['confirmation_token'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ProblemHistory.objects.filter(problem=self.problem, summary='Replied to customer message').exists())
