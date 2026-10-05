from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER, PreparedProblemSample, ProblemContainer, ProblemSample, ProblemHistory, ProblemTrackingLink)
from .views import get_default_table


class PreparedProblemSampleTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='prepare.staff')
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)
        self.table = get_default_table()
        self.container = ProblemContainer.objects.create(created_by=self.staff)
        self.payload = {'table': str(self.table.pk), 'container_code': self.container.container_id,
                        'custom_values': {}}

    def prepare(self):
        response = self.client.post('/api/problem-samples/prepare-new/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ProblemSample.objects.count(), 0)
        return response.data

    def test_cancel_never_creates_sample(self):
        draft = self.prepare()
        response = self.client.post('/api/problem-samples/cancel-prepared/', {'id': draft['id']}, format='json')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(ProblemSample.objects.count(), 0)
        self.assertEqual(ProblemTrackingLink.objects.count(), 0)
        self.assertFalse(PreparedProblemSample.objects.filter(pk=draft['id']).exists())

    def test_did_not_send_creates_only_on_final_click(self):
        draft = self.prepare()
        missing = self.client.post('/api/problem-samples/create-prepared/', {'id': draft['id'], 'sent': False}, format='json')
        blank = self.client.post('/api/problem-samples/create-prepared/', {'id': draft['id'], 'sent': False, 'not_sent_reason': '  '}, format='json')
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(ProblemSample.objects.count(), 0)
        response = self.client.post('/api/problem-samples/create-prepared/', {
            'id': draft['id'], 'sent': False, 'not_sent_reason': '  Email unknown  '
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        sample = ProblemSample.objects.get(pk=response.data['id'])
        self.assertEqual(sample.problem_number, draft['problem_number'])
        self.assertIsNone(sample.customer_notified_at)
        self.assertIsNone(sample.acknowledgement_token)
        self.assertFalse(ProblemTrackingLink.objects.filter(ticket=sample).exists())
        self.assertIsNone(sample.tracking_link_expires_at)
        self.assertEqual(sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        history = ProblemHistory.objects.get(problem=sample, summary='Customer tracking email not sent')
        self.assertEqual(history.details['reason'], 'Email unknown')
        again = self.client.post('/api/problem-samples/create-prepared/', {
            'id': draft['id'], 'sent': False, 'not_sent_reason': 'Email unknown'
        }, format='json')
        self.assertEqual(again.data['id'], response.data['id'])
        self.assertEqual(ProblemSample.objects.count(), 1)

    def test_ticket_can_be_created_without_container(self):
        self.payload.pop('container_code')
        draft = self.prepare()
        response = self.client.post('/api/problem-samples/create-prepared/', {
            'id': draft['id'], 'sent': False, 'not_sent_reason': 'Email unknown',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(ProblemSample.objects.get(pk=response.data['id']).container_id)

    def test_existing_customer_email_attempt_requires_reason_and_records_history(self):
        draft = self.prepare()
        created = self.client.post('/api/problem-samples/create-prepared/', {
            'id': draft['id'], 'sent': False, 'not_sent_reason': 'Email unknown',
        }, format='json')
        endpoint = f"/api/problem-samples/{created.data['id']}/email-not-sent/"
        self.assertEqual(self.client.post(endpoint, {'kind': 'customer'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(endpoint, {'kind': 'customer', 'reason': 'x' * 501}, format='json').status_code, 400)
        response = self.client.post(endpoint, {'kind': 'customer', 'reason': 'Customer address bounced'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProblemHistory.objects.filter(problem_id=created.data['id'], summary='Customer tracking email not sent').count(), 2)
        latest = ProblemHistory.objects.filter(problem_id=created.data['id']).first()
        self.assertEqual(latest.details['reason'], 'Customer address bounced')
        sample = ProblemSample.objects.get(pk=created.data['id'])
        self.assertIsNone(sample.customer_notified_at)
        self.assertIsNone(sample.acknowledgement_token)
        self.assertFalse(ProblemTrackingLink.objects.filter(ticket=sample).exists())
        self.assertIsNone(sample.pending_tracking_token)

    def test_sent_creates_and_records_email_at_final_click(self):
        draft = self.prepare()
        response = self.client.post('/api/problem-samples/create-prepared/', {'id': draft['id'], 'sent': True}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        sample = ProblemSample.objects.get(pk=response.data['id'])
        self.assertIsNotNone(sample.customer_notified_at)
        self.assertTrue(draft['tracking_url'].endswith(sample.acknowledgement_token))
        self.assertEqual(sample.workflow_status, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)
        history = sample.history.get(summary='Sent tracking link to customer by email')
        self.assertIn({'field': 'Current Workflow', 'before': CURRENT_WORKFLOW_DEFAULT, 'after': CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER}, history.details['changes'])

    def test_another_user_cannot_create_or_cancel_preparation(self):
        draft = self.prepare()
        other = APIClient()
        other.force_authenticate(user=User.objects.create_user(username='other.staff'))
        denied = other.post('/api/problem-samples/create-prepared/', {'id': draft['id'], 'sent': True}, format='json')
        self.assertEqual(denied.status_code, 404)
        other.post('/api/problem-samples/cancel-prepared/', {'id': draft['id']}, format='json')
        self.assertTrue(PreparedProblemSample.objects.filter(pk=draft['id']).exists())
        self.assertEqual(ProblemSample.objects.count(), 0)
