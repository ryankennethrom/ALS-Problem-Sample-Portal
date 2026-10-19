"""Manual ticket reactivation always requires an explicit physical destination."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
    PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_BACK_TO_TESTING,
    PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK, TERMINAL_PROBLEM_STATUSES,
    ROUTED_PROBLEM_STATUSES, CURRENT_WORKFLOW_CHOICES,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, ProblemContainer, ProblemHistory, ProblemSample,
)
from .views import get_default_table


class TerminalReactivationContainerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='reactivation.tester')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = get_default_table()
        self.source = ProblemContainer.objects.create(created_by=self.user)
        self.destination = ProblemContainer.objects.create(created_by=self.user)
        self.sample = ProblemSample.objects.create(
            table=self.table, problem_number=710, current_workflow=PROBLEM_STATUS_DISPOSED,
            container=self.source,
            custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_DISPOSED},
        )
        self.url = f'/api/problem-samples/{self.sample.pk}/'

    def switch(self, to=CURRENT_WORKFLOW_DEFAULT, **container_choice):
        return self.client.patch(self.url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: to},
            **container_choice,
        }, format='json')

    def test_transition_requires_explicit_selection_even_with_previous_container(self):
        before_count = ProblemContainer.objects.count()
        response = self.switch()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('container_code', str(response.data))
        self.assertEqual(ProblemContainer.objects.count(), before_count)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, PROBLEM_STATUS_DISPOSED)
        self.assertEqual(self.sample.container_id, self.source.pk)

    def test_assign_existing_container(self):
        response = self.switch(container_code=self.destination.container_id)
        self.assertEqual(response.status_code, 200, response.data)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.container_id, self.destination.pk)
        self.assertEqual(self.sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertTrue(ProblemHistory.objects.filter(problem=self.sample, summary='Saved changes').exists())

    def test_create_new_container_in_same_update(self):
        before_count = ProblemContainer.objects.count()
        response = self.switch(create_new_container=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProblemContainer.objects.count(), before_count + 1)
        self.sample.refresh_from_db()
        self.assertNotEqual(self.sample.container_id, self.source.pk)
        self.assertNotEqual(self.sample.container_id, self.destination.pk)
        self.assertEqual(self.sample.container.created_by_id, self.user.pk)
        self.assertEqual(response.data['container_id'], self.sample.container.container_id)
        self.assertEqual(self.sample.workflow_status, CURRENT_WORKFLOW_DEFAULT)

    def test_cannot_choose_new_and_existing_together(self):
        response = self.switch(container_code=self.destination.container_id, create_new_container=True)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ProblemContainer.objects.count(), 2)

    def test_cannot_reopen_into_disposed_or_dumping_container(self):
        dump = ProblemContainer.objects.create(created_by=self.user, is_dumping=True)
        response = self.switch(container_code=dump.container_id)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ProblemContainer.objects.count(), 3)

    def test_must_undo_dumping_container_disposal_before_reopening(self):
        self.source.is_dumping = True
        self.source.save(update_fields=['is_dumping'])
        response = self.switch(create_new_container=True)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('Undo', str(response.data))
        self.assertEqual(ProblemContainer.objects.count(), 2)

    def test_editing_terminal_ticket_without_workflow_change_is_allowed(self):
        response = self.client.patch(self.url, {'issue_description': 'Additional notes'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.workflow_status, PROBLEM_STATUS_DISPOSED)
        self.assertEqual(self.sample.issue_description, 'Additional notes')

    def test_nonterminal_to_nonterminal_needs_no_container(self):
        self.sample.set_workflow_status(CURRENT_WORKFLOW_DEFAULT)
        self.sample.container = None
        self.sample.save(update_fields=['current_workflow', 'custom_values', 'container'])
        response = self.switch(CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)
        self.assertEqual(response.status_code, 200, response.data)
        self.sample.refresh_from_db()
        self.assertIsNone(self.sample.container_id)

    def test_only_three_completed_workflows_are_terminal(self):
        self.assertEqual(set(TERMINAL_PROBLEM_STATUSES), {
            PROBLEM_STATUS_DISPOSED,
            PROBLEM_STATUS_SHIPPED_BACK,
            PROBLEM_STATUS_BACK_TO_TESTING,
        })
        self.assertEqual(set(ROUTED_PROBLEM_STATUSES), set(CURRENT_WORKFLOW_CHOICES) - {
            CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
        })

    def test_pending_workflow_to_nonterminal_needs_no_new_container(self):
        for pending in (
            PROBLEM_STATUS_TO_BE_DISPOSED,
            PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
            PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
        ):
            with self.subTest(pending=pending):
                self.sample.set_workflow_status(pending)
                self.sample.container = None
                self.sample.save(update_fields=['current_workflow', 'custom_values', 'container'])
                response = self.switch()
                self.assertEqual(response.status_code, 200, response.data)
                self.sample.refresh_from_db()
                self.assertIsNone(self.sample.container_id)

    def test_each_terminal_to_each_nonterminal_requires_container(self):
        nonterminal = [
            CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
            PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
            PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
        ]
        for terminal in TERMINAL_PROBLEM_STATUSES:
            for destination in nonterminal:
                with self.subTest(source=terminal, destination=destination):
                    self.sample.set_workflow_status(terminal)
                    self.sample.container = None
                    self.sample.save(update_fields=['current_workflow', 'custom_values', 'container'])
                    missing = self.switch(destination)
                    self.assertEqual(missing.status_code, 400, missing.data)
                    self.assertIn('container_code', str(missing.data))
                    self.sample.refresh_from_db()
                    self.assertEqual(self.sample.workflow_status, terminal)

    def test_shipped_terminal_return_to_nonterminal_requires_container(self):
        self.sample.set_workflow_status(PROBLEM_STATUS_SHIPPED_BACK)
        self.sample.container = None
        self.sample.save(update_fields=['current_workflow', 'custom_values', 'container'])
        missing = self.switch()
        self.assertEqual(missing.status_code, 400, missing.data)
        restored = self.switch(container_code=self.destination.container_id)
        self.assertEqual(restored.status_code, 200, restored.data)
