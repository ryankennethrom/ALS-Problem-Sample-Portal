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


class BackToTestingEmailTests(TestCase):
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

    def update_workflow(self, workflow, decision=None):
        payload = {'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: workflow}}
        if decision is not None:
            payload.update(back_to_testing_email_sent=decision, back_to_testing_email_body='Please retest this sample.', email_recipient='NAEDM.DE@ALSGlobal.com')
            if decision is False:
                payload['back_to_testing_not_sent_reason'] = 'Email unknown'
        return self.client.patch(self.url, payload, format='json')

    def test_transition_requires_confirmation_and_can_be_notified_later(self):
        rejected = self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertEqual(rejected.status_code, 400)
        no_reason = self.client.patch(self.url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
            'back_to_testing_email_sent': False,
        }, format='json')
        self.assertEqual(no_reason.status_code, 400)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)

        changed = self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING, False)
        self.assertEqual(changed.status_code, 200)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertIsNone(self.sample.back_to_testing_notified_at)
        not_sent = ProblemHistory.objects.get(problem=self.sample, summary='Back to Testing email not sent to NA.EDM')
        self.assertEqual(not_sent.details['reason'], 'Email unknown')
        queue = self.client.get('/api/problem-samples/back-to-testing/')
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.data[0]['id'], str(self.sample.pk))
        self.assertIsNone(queue.data[0]['back_to_testing_notified_at'])

        sent_url = f'{self.url}back-to-testing-notification/'
        sent = self.client.post(sent_url, {'email_body': 'Please retest this sample.', 'email_recipient': 'NAEDM.DE@ALSGlobal.com'}, format='json')
        self.assertEqual(sent.status_code, 200)
        self.sample.refresh_from_db()
        self.assertIsNotNone(self.sample.back_to_testing_notified_at)
        self.assertTrue(ProblemHistory.objects.filter(problem=self.sample, summary='Sent Back to Testing email to NA.EDM').exists())
        self.assertEqual(self.client.post(sent_url, {'email_body': 'Repeated', 'email_recipient': 'NAEDM.DE@ALSGlobal.com'}, format='json').status_code, 409)

    def test_retry_not_sent_requires_reason_and_leaves_notification_pending(self):
        self.assertEqual(self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING, False).status_code, 200)
        endpoint = f'{self.url}email-not-sent/'
        self.assertEqual(self.client.post(endpoint, {'kind': 'back_to_testing', 'reason': '  '}, format='json').status_code, 400)
        response = self.client.post(endpoint, {'kind': 'back_to_testing', 'reason': '  Wrong address  '}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProblemHistory.objects.filter(problem=self.sample, summary='Back to Testing email not sent to NA.EDM').count(), 2)
        self.assertEqual(ProblemHistory.objects.filter(problem=self.sample).first().details['reason'], 'Wrong address')
        self.sample.refresh_from_db()
        self.assertIsNone(self.sample.back_to_testing_notified_at)

    def test_confirmed_email_is_recorded_with_workflow_transition(self):
        missing_body = self.client.patch(self.url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
            'back_to_testing_email_sent': True,
        }, format='json')
        self.assertEqual(missing_body.status_code, 400)
        response = self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING, True)
        self.assertEqual(response.status_code, 200)
        self.sample.refresh_from_db()
        self.assertIsNotNone(self.sample.back_to_testing_notified_at)
        history = ProblemHistory.objects.get(problem=self.sample, summary='Sent Back to Testing email to NA.EDM')
        self.assertEqual(history.details['recipient'], 'NAEDM.DE@ALSGlobal.com')
        self.assertEqual(history.details['email_body'], 'Please retest this sample.')
        self.assertEqual(self.update_workflow(CURRENT_WORKFLOW_DEFAULT).status_code, 200)
        self.sample.refresh_from_db()
        self.assertIsNone(self.sample.back_to_testing_notified_at)

    def test_custom_address_is_recorded_and_stale_preview_is_rejected(self):
        from accounts.models import UserProfile
        admin = User.objects.create_user(username='testing.admin', password='test-password')
        UserProfile.objects.create(user=admin, is_admin=True)
        self.client.force_authenticate(admin)
        changed = self.client.put('/api/email-templates/edmonton-recipient/', {'email': 'updated.edm@example.com'}, format='json')
        self.assertEqual(changed.status_code, 200)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/email-templates/edmonton-recipient/').data['email'], 'updated.edm@example.com')
        self.assertEqual(self.update_workflow(PROBLEM_STATUS_BACK_TO_TESTING, True).status_code, 400)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        sent = self.client.patch(self.url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
            'back_to_testing_email_sent': True,
            'back_to_testing_email_body': 'Please retest.',
            'email_recipient': 'updated.edm@example.com',
        }, format='json')
        self.assertEqual(sent.status_code, 200)
        history = ProblemHistory.objects.get(problem=self.sample, summary='Sent Back to Testing email to NA.EDM')
        self.assertEqual(history.details['recipient'], 'updated.edm@example.com')

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
