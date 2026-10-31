from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    PROBLEM_STATUS_BACK_TO_TESTING, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, ProblemContainer, ProblemHistory, ProblemSample,
)
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

    def test_bulk_completion_requires_no_email_and_records_only_workflow_changes(self):
        response = self.client.post(self.url, self.payload(), format='json', HTTP_X_CHANGE_REASON='Ready for testing')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 2)
        self.assertNotIn('emails_sent_confirmed', response.data)
        self.assertNotIn('email_batch_id', response.data)
        for sample in (self.first, self.second):
            sample.refresh_from_db()
            self.assertEqual(sample.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
            self.assertIsNone(sample.container_id)
            self.assertIsNone(sample.back_to_testing_notified_at)
            entry = ProblemHistory.objects.get(problem=sample, summary='Moved back to testing')
            self.assertEqual(entry.details['reason'], 'Ready for testing')
            self.assertNotIn('email_status', entry.details)
            self.assertNotIn('email_batch_id', entry.details)
        self.assertFalse(ProblemHistory.objects.filter(summary__icontains='Back to Testing email').exists())
        self.assertEqual(len(self.client.get('/api/problem-samples/to-be-back-to-testing/').data), 0)

    def test_stale_ticket_blocks_entire_batch(self):
        stale = self.sample(3)
        stale.current_workflow = 'Follow Up Required'
        stale.custom_values = {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: 'Follow Up Required'}
        stale.save(update_fields=['current_workflow', 'custom_values'])
        response = self.client.post(self.url, {'problem_ids': [str(self.first.pk), str(stale.pk)]}, format='json')
        self.assertEqual(response.status_code, 409)
        self.first.refresh_from_db()
        self.assertEqual(self.first.workflow_status, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        self.assertEqual(self.first.container_id, self.container.pk)
        self.assertFalse(ProblemHistory.objects.filter(problem=self.first).exists())

    def test_disposed_container_blocks_entire_batch(self):
        another = ProblemContainer.objects.create(created_by=self.user, disposed_at=timezone.now())
        self.second.container = another
        self.second.save(update_fields=['container'])
        response = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(response.status_code, 409, response.data)
        self.first.refresh_from_db()
        self.assertEqual(self.first.workflow_status, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        self.assertEqual(self.first.container_id, self.container.pk)

    def test_batch_handles_tickets_with_nullable_container_and_table(self):
        """PostgreSQL rejects FOR UPDATE applied to nullable outer-joined tables."""
        self.first.container = None
        self.first.table = None
        self.first.save(update_fields=['container', 'table'])
        self.second.container = None
        self.second.save(update_fields=['container'])
        response = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertEqual(self.second.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)

    def test_repeat_submission_is_rejected_without_extra_history(self):
        payload = self.payload()
        self.assertEqual(self.client.post(self.url, payload, format='json').status_code, 200)
        self.assertEqual(self.client.post(self.url, payload, format='json').status_code, 409)
        self.assertEqual(ProblemHistory.objects.filter(summary='Moved back to testing').count(), 2)
        self.assertFalse(ProblemHistory.objects.filter(summary__icontains='Back to Testing email').exists())
