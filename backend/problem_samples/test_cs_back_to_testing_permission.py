"""Customer Service may never initiate a transition to Back to testing."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import (
    CURRENT_WORKFLOW_DEFAULT,
    PROBLEM_STATUS_BACK_TO_TESTING,
    PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    ProblemHistory,
    ProblemSample,
)
from .views import get_default_table


class CustomerServiceBackToTestingPermissionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='customer.service.test')
        self.profile = UserProfile.objects.create(
            user=self.staff, role=UserProfile.ROLE_CUSTOMER_SERVICE,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.table = get_default_table()
        self.ticket = ProblemSample.objects.create(
            table=self.table, problem_number=1,
            current_workflow=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
            custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_TO_BE_BACK_TO_TESTING},
        )
        self.ticket_url = f'/api/problem-samples/{self.ticket.pk}/'
        self.bulk_url = '/api/problem-samples/bulk-back-to-testing/'

    def test_customer_service_cannot_patch_to_back_to_testing(self):
        response = self.client.patch(self.ticket_url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
            'back_to_testing_email_sent': False,
            'back_to_testing_not_sent_reason': 'Email unavailable',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('Customer Service', str(response.data))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        self.assertFalse(ProblemHistory.objects.filter(problem=self.ticket).exists())

    def test_admin_with_customer_service_role_is_still_restricted(self):
        self.profile.is_admin = True
        self.profile.save(update_fields=['is_admin'])
        response = self.client.patch(self.ticket_url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
            'back_to_testing_email_sent': False,
            'back_to_testing_not_sent_reason': 'Email unavailable',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_bulk_return_to_testing_is_forbidden_without_side_effects(self):
        second = ProblemSample.objects.create(
            table=self.table, problem_number=2,
            current_workflow=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
            custom_values={SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_TO_BE_BACK_TO_TESTING},
        )
        response = self.client.post(self.bulk_url, {
            'problem_ids': [str(self.ticket.pk), str(second.pk)],
            'back_to_testing_email_sent': False,
            'back_to_testing_not_sent_reason': 'Email unavailable',
        }, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.ticket.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        self.assertEqual(second.workflow_status, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        self.assertEqual(ProblemHistory.objects.count(), 0)

    def test_other_workflow_changes_remain_allowed(self):
        response = self.client.patch(self.ticket_url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT},
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, CURRENT_WORKFLOW_DEFAULT)

    def test_existing_back_to_testing_ticket_can_be_edited_without_transition(self):
        self.ticket.current_workflow = PROBLEM_STATUS_BACK_TO_TESTING
        self.ticket.custom_values = {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING}
        self.ticket.save(update_fields=['current_workflow', 'custom_values'])
        response = self.client.patch(self.ticket_url, {'issue_description': 'Edited note'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
        self.assertEqual(self.ticket.issue_description, 'Edited note')

    def test_customer_service_cannot_prepare_a_ticket_in_back_to_testing(self):
        response = self.client.post('/api/problem-samples/prepare-new/', {
            'table': str(self.table.pk),
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('Customer Service', str(response.data))

    def test_lab_staff_can_still_change_workflow_to_back_to_testing(self):
        self.profile.role = UserProfile.ROLE_LAB_TECHNICIAN
        self.profile.save(update_fields=['role'])
        response = self.client.patch(self.ticket_url, {
            'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: PROBLEM_STATUS_BACK_TO_TESTING},
            'back_to_testing_email_sent': False,
            'back_to_testing_not_sent_reason': 'Email unavailable',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.workflow_status, PROBLEM_STATUS_BACK_TO_TESTING)
