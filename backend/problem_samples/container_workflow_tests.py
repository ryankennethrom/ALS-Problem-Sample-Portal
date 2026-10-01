from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT, PROBLEM_STATUS_BACK_TO_TESTING, PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, ProblemContainer, ProblemHistory, ProblemSample,
)
from .views import get_default_table


class OptionalContainerWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='container.workflow')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = get_default_table()
        self.container = ProblemContainer.objects.create(created_by=self.user)

    def sample(self, number, workflow=CURRENT_WORKFLOW_DEFAULT, container=None):
        return ProblemSample.objects.create(
            table=self.table, problem_number=number, current_workflow=workflow,
            container=container, custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: workflow},
        )

    def container_state(self):
        return self.client.get(f'/api/problem-containers/{self.container.pk}/').data

    def test_optional_container_can_be_assigned_and_removed(self):
        prepared = self.client.post('/api/problem-samples/prepare-new/', {
            'table': str(self.table.pk), 'custom_values': {},
        }, format='json')
        self.assertEqual(prepared.status_code, 201, prepared.data)
        created = self.client.post('/api/problem-samples/create-prepared/', {
            'id': prepared.data['id'], 'sent': False, 'not_sent_reason': 'Email unknown',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        ticket = ProblemSample.objects.get(pk=created.data['id'])
        self.assertIsNone(ticket.container_id)
        url = f'/api/problem-samples/{ticket.pk}/'
        assigned = self.client.patch(url, {'container_code': self.container.container_id}, format='json')
        self.assertEqual(assigned.status_code, 200, assigned.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.container_id, self.container.pk)
        removed = self.client.patch(url, {'container_code': ''}, format='json')
        self.assertEqual(removed.status_code, 200, removed.data)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.container_id)

    def test_pending_testing_blocks_disposal_and_final_testing_detaches(self):
        ticket = self.sample(1, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING, self.container)
        self.assertFalse(self.container_state()['ready_to_dispose'])
        queue = self.client.get('/api/problem-samples/to-be-back-to-testing/')
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.data[0]['id'], str(ticket.pk))
        changed = self.client.patch(f'/api/problem-samples/{ticket.pk}/', {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
            'back_to_testing_email_sent': False,
            'back_to_testing_not_sent_reason': 'Email unknown',
        }, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertIsNone(ticket.container_id)
        self.assertEqual(self.container_state()['status'], 'empty')
        changes = ProblemHistory.objects.filter(problem=ticket, summary='Saved changes').first().details['changes']
        self.assertTrue(any(change['field'] == 'Container ID' for change in changes))

    def test_shipped_ticket_detaches_and_remaining_disposed_ticket_is_ready(self):
        shipped = self.sample(1, PROBLEM_STATUS_TO_BE_SHIPPED_BACK, self.container)
        disposed = self.sample(2, PROBLEM_STATUS_DISPOSED, self.container)
        self.assertFalse(self.container_state()['ready_to_dispose'])
        result = self.client.post('/api/problem-samples/bulk-ship-back/', {
            'problem_ids': [str(shipped.pk)],
        }, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        shipped.refresh_from_db()
        self.assertEqual(shipped.workflow_status, PROBLEM_STATUS_SHIPPED_BACK)
        self.assertIsNone(shipped.container_id)
        self.assertEqual(self.container_state()['status'], 'ready_to_dispose')
        result = self.client.post(f'/api/problem-containers/{self.container.pk}/dispose/', {}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['status'], 'disposed')
        disposed.refresh_from_db()
        self.assertEqual(disposed.workflow_status, PROBLEM_STATUS_DISPOSED)
        undone = self.client.post(f'/api/problem-containers/{self.container.pk}/undo-disposal/', {}, format='json')
        self.assertEqual(undone.status_code, 200, undone.data)
        disposed.refresh_from_db()
        self.assertEqual(disposed.workflow_status, PROBLEM_STATUS_DISPOSED)

    def test_mixed_disposal_waiting_and_disposed_tickets_are_ready(self):
        waiting = self.sample(1, PROBLEM_STATUS_TO_BE_DISPOSED, self.container)
        already_disposed = self.sample(2, PROBLEM_STATUS_DISPOSED, self.container)
        self.assertTrue(self.container_state()['ready_to_dispose'])
        result = self.client.post(f'/api/problem-containers/{self.container.pk}/dispose/', {}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        waiting.refresh_from_db()
        already_disposed.refresh_from_db()
        self.assertEqual(waiting.workflow_status, PROBLEM_STATUS_DISPOSED)
        self.assertEqual(already_disposed.workflow_status, PROBLEM_STATUS_DISPOSED)
        self.container.refresh_from_db()
        self.assertEqual(set(self.container.disposal_snapshot), {str(waiting.pk)})
        undone = self.client.post(f'/api/problem-containers/{self.container.pk}/undo-disposal/', {}, format='json')
        self.assertEqual(undone.status_code, 200, undone.data)
        waiting.refresh_from_db()
        already_disposed.refresh_from_db()
        self.assertEqual(waiting.workflow_status, PROBLEM_STATUS_TO_BE_DISPOSED)
        self.assertEqual(already_disposed.workflow_status, PROBLEM_STATUS_DISPOSED)

    def set_created_days_ago(self, ticket, days):
        created_at = timezone.now() - timedelta(days=days)
        ProblemSample.objects.filter(pk=ticket.pk).update(created_at=created_at)
        ticket.refresh_from_db()
        return ticket

    def test_dispose_by_date_allows_non_ready_container_when_every_ticket_is_older(self):
        first = self.set_created_days_ago(self.sample(10, CURRENT_WORKFLOW_DEFAULT, self.container), 20)
        second = self.set_created_days_ago(self.sample(11, PROBLEM_STATUS_TO_BE_SHIPPED_BACK, self.container), 15)
        cutoff = (timezone.localdate() - timedelta(days=10)).isoformat()

        state = self.container_state()
        self.assertFalse(state['ready_to_dispose'])
        self.assertEqual(state['samples'][0]['created_date'], timezone.localdate(state['samples'][0]['created_at']).isoformat())

        result = self.client.post(
            f'/api/problem-containers/{self.container.pk}/dispose-by-date/',
            {'cutoff_date': cutoff}, format='json',
            HTTP_X_CHANGE_REASON='Old physical container cleanup',
        )
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['status'], 'disposed')

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.workflow_status, PROBLEM_STATUS_DISPOSED)
        self.assertEqual(second.workflow_status, PROBLEM_STATUS_DISPOSED)
        self.container.refresh_from_db()
        self.assertEqual(set(self.container.disposal_snapshot), {str(first.pk), str(second.pk)})

        history = ProblemHistory.objects.filter(problem=first, summary=f'Container {self.container.container_id} disposed').latest('created_at')
        self.assertEqual(history.details['disposal_method'], 'dispose_by_date')
        self.assertEqual(history.details['cutoff_date'], cutoff)
        self.assertEqual(history.details['reason'], 'Old physical container cleanup')

        undone = self.client.post(f'/api/problem-containers/{self.container.pk}/undo-disposal/', {}, format='json')
        self.assertEqual(undone.status_code, 200, undone.data)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(second.workflow_status, PROBLEM_STATUS_TO_BE_SHIPPED_BACK)

    def test_dispose_by_date_rejects_container_when_any_ticket_is_not_old_enough(self):
        old_ticket = self.set_created_days_ago(self.sample(20, CURRENT_WORKFLOW_DEFAULT, self.container), 20)
        recent_ticket = self.set_created_days_ago(self.sample(21, CURRENT_WORKFLOW_DEFAULT, self.container), 2)
        cutoff = (timezone.localdate() - timedelta(days=10)).isoformat()

        result = self.client.post(
            f'/api/problem-containers/{self.container.pk}/dispose-by-date/',
            {'cutoff_date': cutoff}, format='json',
        )
        self.assertEqual(result.status_code, 409, result.data)
        self.assertIn(recent_ticket.problem_number, result.data['blocking_problem_ids'])
        self.assertNotIn(old_ticket.problem_number, result.data['blocking_problem_ids'])

        self.container.refresh_from_db()
        old_ticket.refresh_from_db()
        recent_ticket.refresh_from_db()
        self.assertIsNone(self.container.disposed_at)
        self.assertEqual(old_ticket.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(recent_ticket.workflow_status, CURRENT_WORKFLOW_DEFAULT)

    def test_dispose_by_date_is_strict_for_tickets_created_on_cutoff_date(self):
        ticket = self.sample(30, CURRENT_WORKFLOW_DEFAULT, self.container)
        cutoff = timezone.localdate().isoformat()
        result = self.client.post(
            f'/api/problem-containers/{self.container.pk}/dispose-by-date/',
            {'cutoff_date': cutoff}, format='json',
        )
        self.assertEqual(result.status_code, 409, result.data)
        self.assertEqual(result.data['blocking_problem_ids'], [ticket.problem_number])

