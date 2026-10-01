from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    PROBLEM_STATUS_BACK_TO_TESTING, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, ProblemContainer, ProblemHistory, ProblemSample,
)
from .notification_recipient import get_edmonton_recipient
from .views import get_default_table


class BulkBackToTestingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='bulk.testing')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = get_default_table()
        self.container = ProblemContainer.objects.create(created_by=self.user)
        self.first = self.sample(1)
        self.second = self.sample(2)
        self.url = '/api/problem-samples/bulk-back-to-testing/'

    def sample(self, number, container=None):
        return ProblemSample.objects.create(
            table=self.table, problem_number=number,
            container=self.container if container is None else container,
            current_workflow=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
            custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_TO_BE_BACK_TO_TESTING},
        )

    def payload(self, **changes):
        return {'problem_ids': [str(self.first.pk), str(self.second.pk)], **changes}

    def test_bulk_completion_requires_email_decision_and_is_atomic(self):
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 400)
        self.assertEqual(self.client.post(self.url, self.payload(back_to_testing_email_sent=False), format='json').status_code, 400)
        self.assertEqual(self.client.post(self.url, self.payload(back_to_testing_email_sent=True,
            back_to_testing_email_body='Please retest.'), format='json').status_code, 400)
        stale = self.sample(3)
        stale.current_workflow = 'CS Follow-Up'
        stale.custom_values = {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: 'CS Follow-Up'}
        stale.save(update_fields=['current_workflow', 'custom_values'])
        self.assertEqual(self.client.post(self.url, {
            'problem_ids': [str(self.first.pk), str(stale.pk)], 'back_to_testing_email_sent': False,
            'back_to_testing_not_sent_reason': 'Email unknown',
        }, format='json').status_code, 409)
        self.first.refresh_from_db()
        self.assertEqual(self.first.workflow_status, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        self.assertEqual(self.first.container_id, self.container.pk)

        response = self.client.post(self.url, self.payload(back_to_testing_email_sent=True,
            back_to_testing_email_body='Please retest both samples.',
            email_recipient=get_edmonton_recipient().email), format='json', HTTP_X_CHANGE_REASON='Samples are ready')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 2)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        for sample in (self.first, self.second):
            self.assertEqual(sample.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
            self.assertIsNone(sample.container_id)
            self.assertIsNotNone(sample.back_to_testing_notified_at)
            self.assertTrue(ProblemHistory.objects.filter(problem=sample, summary='Moved back to testing',
                                                           details__reason='Samples are ready').exists())
            self.assertTrue(ProblemHistory.objects.filter(problem=sample,
                                                           summary='Sent Back to Testing email to NA.EDM').exists())
        self.assertEqual(len(self.client.get('/api/problem-samples/to-be-back-to-testing/').data), 0)

    def test_no_email_keeps_notification_pending_and_requires_reason(self):
        response = self.client.post(self.url, self.payload(back_to_testing_email_sent=False,
            back_to_testing_not_sent_reason='Email unknown'), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.first.refresh_from_db()
        self.assertEqual(self.first.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertIsNone(self.first.container_id)
        self.assertIsNone(self.first.back_to_testing_notified_at)
        self.assertEqual(ProblemHistory.objects.get(problem=self.first,
            summary='Back to Testing email not sent to NA.EDM').details['reason'], 'Email unknown')

    def test_disposed_container_blocks_entire_batch(self):
        another = ProblemContainer.objects.create(created_by=self.user, disposed_at=timezone.now())
        self.second.container = another
        self.second.save(update_fields=['container'])
        response = self.client.post(self.url, self.payload(back_to_testing_email_sent=False,
            back_to_testing_not_sent_reason='Email unknown'), format='json')
        self.assertEqual(response.status_code, 409, response.data)
        self.first.refresh_from_db()
        self.assertEqual(self.first.workflow_status, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        self.assertEqual(self.first.container_id, self.container.pk)
