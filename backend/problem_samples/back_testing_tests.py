from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .views import ensure_builtin_columns
from .models import (
    CURRENT_WORKFLOW_DEFAULT, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING, PROBLEM_STATUS_BACK_TO_TESTING, PROBLEM_STATUS_DEFAULT,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
    ProblemHistory, ProblemSample, ProblemTrackingLink, ProblemTable, generate_acknowledgement_token,
)


class BackToTestingWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testing.staff', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = ProblemTable.objects.create(name='Testing email table', is_default=True)
        ensure_builtin_columns(self.table)
        self.sample = ProblemSample.objects.create(
            table=self.table, problem_number=1, status=PROBLEM_STATUS_DEFAULT,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={'status': PROBLEM_STATUS_DEFAULT,
                           SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                           SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: 'No'},
        )
        ProblemTrackingLink.objects.create(ticket=self.sample, tracking_token=generate_acknowledgement_token())
        self.url = f'/api/problem-samples/{self.sample.pk}/'

    def update_workflow(self, workflow):
        return self.client.patch(self.url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: workflow},
        }, format='json')

    def test_transition_without_email_preserves_workflow_and_history(self):
        changed = self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertEqual(changed.status_code, 200, changed.data)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertIsNone(self.sample.back_to_testing_notified_at)
        entries = ProblemHistory.objects.filter(problem=self.sample)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().summary, 'Saved changes')
        self.assertFalse(entries.filter(summary__icontains='email').exists())
        queue = self.client.get('/api/problem-samples/back-to-testing/')
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.data[0]['id'], str(self.sample.pk))

    def test_reopening_ticket_remains_supported(self):
        self.assertEqual(self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING).status_code, 200)
        self.assertEqual(self.update_workflow(CURRENT_WORKFLOW_DEFAULT).status_code, 200)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertIsNone(self.sample.back_to_testing_notified_at)

    def test_obsolete_notification_endpoint_is_not_available(self):
        self.assertEqual(self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING).status_code, 200)
        self.assertEqual(self.client.post(f'{self.url}back-to-testing-notification/', {
            'email_body': 'Please retest this sample.',
        }, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'{self.url}email-not-sent/', {
            'kind': 'back_to_testing', 'reason': 'Not required',
        }, format='json').status_code, 400)

    def test_customer_requested_information_stays_in_follow_up(self):
        response = self.client.post(f'/api/public/problem-sample-tracking/{self.sample.acknowledgement_token}/',
            {'action': 'requested_info', 'signature': 'Customer Name',
             'requested_information': 'Please check the contamination.'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(self.sample.custom_values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY], CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(self.sample.customer_acknowledgement_action, 'requested_info')
        self.assertIsNone(self.sample.back_to_testing_notified_at)
        queue = self.client.get('/api/problem-samples/to-be-back-to-testing/')
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.data, [])
        follow_up = self.client.get('/api/problem-samples/follow-up-required/', {'table': str(self.table.pk)})
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(follow_up.data[0]['id'], str(self.sample.pk))
        self.assertEqual(self.client.get('/api/dashboard/').data['counts']['customer_responded'], 1)
        response_history = ProblemHistory.objects.get(problem=self.sample, summary='Customer selected: Message us about the issue')
        self.assertEqual(response_history.details['customer_requested_information'], 'Please check the contamination.')

    def test_customer_requested_information_stops_automatic_disposal(self):
        values = dict(self.sample.custom_values)
        values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = 'Yes'
        ProblemSample.objects.filter(pk=self.sample.pk).update(
            custom_values=values, automatic_disposal_started_at=timezone.now()
        )

        response = self.client.post(f'/api/public/problem-sample-tracking/{self.sample.acknowledgement_token}/',
            {'action': 'requested_info', 'signature': 'Customer Name',
             'requested_information': 'Please review the attachment.'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertFalse(self.sample.dispose_automatically)
        self.assertIsNone(self.sample.expires_at)
        self.assertEqual(self.sample.customer_acknowledgement_action, 'requested_info')
