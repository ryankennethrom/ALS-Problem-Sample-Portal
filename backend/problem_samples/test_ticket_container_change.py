"""API regression coverage for the ticket-page Change Container popup."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT, PROBLEM_STATUS_DISPOSED,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, ProblemContainer, ProblemHistory, ProblemSample,
)
from .views import get_default_table


class TicketContainerChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='container.change')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = get_default_table()
        self.old_container = ProblemContainer.objects.create(created_by=self.user)
        self.existing_container = ProblemContainer.objects.create(created_by=self.user)
        self.ticket = ProblemSample.objects.create(
            table=self.table, problem_number=9231,
            current_workflow=CURRENT_WORKFLOW_DEFAULT, container=self.old_container,
            custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT},
        )
        self.url = f'/api/problem-samples/{self.ticket.pk}/'

    def update(self, **data):
        return self.client.patch(self.url, data, format='json')

    def test_switch_to_existing_container_without_workflow_change(self):
        response = self.update(container_code=self.existing_container.container_id)
        self.assertEqual(response.status_code, 200, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.container_id, self.existing_container.pk)
        self.assertEqual(self.ticket.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        entry = ProblemHistory.objects.filter(problem=self.ticket, summary='Saved changes').latest('created_at')
        self.assertTrue(any(item['field'] == 'Container ID' for item in entry.details['changes']))

    def test_create_new_container_without_workflow_change(self):
        old_count = ProblemContainer.objects.count()
        response = self.update(create_new_container=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual(ProblemContainer.objects.count(), old_count + 1)
        self.assertNotIn(self.ticket.container_id, (self.old_container.pk, self.existing_container.pk))
        self.assertEqual(self.ticket.container.created_by_id, self.user.pk)
        self.assertEqual(response.data['container_id'], self.ticket.container.container_id)
        self.assertEqual(self.ticket.workflow_status, CURRENT_WORKFLOW_DEFAULT)

    def test_unassigned_ticket_can_create_container(self):
        self.ticket.container = None
        self.ticket.save(update_fields=['container'])
        response = self.update(create_new_container=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.container_id)

    def test_invalid_existing_id_does_not_move_ticket(self):
        response = self.update(container_code='PC-DOES-NOT-EXIST')
        self.assertEqual(response.status_code, 400, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.container_id, self.old_container.pk)

    def test_cannot_choose_both_new_and_existing(self):
        response = self.update(create_new_container=True, container_code=self.existing_container.container_id)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ProblemContainer.objects.count(), 2)

    def test_cannot_move_into_dumping_container(self):
        self.existing_container.is_dumping = True
        self.existing_container.save(update_fields=['is_dumping'])
        response = self.update(container_code=self.existing_container.container_id)
        self.assertEqual(response.status_code, 400, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.container_id, self.old_container.pk)

    def test_cannot_move_out_of_dumping_container_by_creating_new(self):
        self.old_container.is_dumping = True
        self.old_container.save(update_fields=['is_dumping'])
        response = self.update(create_new_container=True)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ProblemContainer.objects.count(), 2)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.container_id, self.old_container.pk)

    def test_cannot_create_new_container_while_ticket_is_terminal(self):
        self.ticket.set_workflow_status(PROBLEM_STATUS_DISPOSED)
        self.ticket.save(update_fields=['current_workflow', 'custom_values'])
        response = self.update(create_new_container=True)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ProblemContainer.objects.count(), 2)

    def test_invalid_custom_values_do_not_leave_new_container(self):
        response = self.update(create_new_container=True, custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: 'Not a workflow'})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ProblemContainer.objects.count(), 2)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.container_id, self.old_container.pk)
