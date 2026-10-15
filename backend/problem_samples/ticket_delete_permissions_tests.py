from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import ProblemSample, ProblemTable


class TicketDeletePermissionsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username='ticket.staff', password='test-password')
        self.admin_user = User.objects.create_user(username='ticket.admin', password='test-password')
        UserProfile.objects.create(user=self.staff_user, is_admin=False)
        UserProfile.objects.create(user=self.admin_user, is_admin=True)

        self.staff = APIClient()
        self.staff.force_authenticate(self.staff_user)
        self.admin = APIClient()
        self.admin.force_authenticate(self.admin_user)

        self.table = ProblemTable.objects.create(name='Ticket deletion permissions', is_default=True)

    def make_ticket(self, number):
        return ProblemSample.objects.create(table=self.table, problem_number=number)

    def test_non_admin_cannot_delete_ticket(self):
        ticket = self.make_ticket(1)
        response = self.staff.delete(f'/api/problem-samples/{ticket.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['detail'], 'Only administrators can delete tickets.')
        self.assertTrue(ProblemSample.objects.filter(pk=ticket.pk).exists())

    def test_admin_can_delete_ticket(self):
        ticket = self.make_ticket(2)
        response = self.admin.delete(f'/api/problem-samples/{ticket.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProblemSample.objects.filter(pk=ticket.pk).exists())
