"""Lab administration permissions and reference-safe deletion.
Run with: python manage.py test accounts.test_lab_management
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Lab, UserProfile
from problem_samples.models import LabEmailTemplate, ProblemSample, ProblemTable


class LabManagementTests(TestCase):
    def setUp(self):
        self.edmonton = Lab.objects.get(code='EDM')
        self.calgary = Lab.objects.create(name='Calgary', code='CGY')
        self.admin = User.objects.create_user(username='admin-labs', password='secret')
        UserProfile.objects.create(user=self.admin, role='lab_technician', is_admin=True, lab=self.edmonton)
        self.staff = User.objects.create_user(username='staff-labs', password='secret')
        UserProfile.objects.create(user=self.staff, role='lab_technician', lab=self.edmonton)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_add_a_lab(self):
        result = self.client.post('/api/auth/labs/', {'name': 'Vancouver', 'code': 'VAN'}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertTrue(Lab.objects.filter(name='Vancouver', code='VAN').exists())

    def test_admin_can_rename_but_cannot_change_code(self):
        result = self.client.patch(f'/api/auth/labs/{self.calgary.pk}/', {'name': 'Calgary East'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.calgary.refresh_from_db()
        self.assertEqual(self.calgary.name, 'Calgary East')
        self.assertEqual(self.calgary.code, 'CGY')
        rejected = self.client.patch(f'/api/auth/labs/{self.calgary.pk}/', {'code': 'NEW'}, format='json')
        self.assertEqual(rejected.status_code, 400)
        self.calgary.refresh_from_db()
        self.assertEqual(self.calgary.code, 'CGY')

    def test_rejects_duplicate_and_invalid_lab_names(self):
        self.assertEqual(self.client.patch(f'/api/auth/labs/{self.calgary.pk}/', {'name': 'edmonton'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/auth/labs/{self.calgary.pk}/', {'name': '  '}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/labs/', {'name': 'CALGARY', 'code': 'AAA'}, format='json').status_code, 400)

    def test_empty_lab_can_be_deleted(self):
        response = self.client.delete(f'/api/auth/labs/{self.calgary.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Lab.objects.filter(pk=self.calgary.pk).exists())

    def test_lab_with_staff_cannot_be_deleted(self):
        UserProfile.objects.filter(user=self.staff).update(lab=self.calgary)
        result = self.client.delete(f'/api/auth/labs/{self.calgary.pk}/')
        self.assertEqual(result.status_code, 409, result.data)
        self.assertIn('Staff accounts', result.data['references'])
        self.assertTrue(Lab.objects.filter(pk=self.calgary.pk).exists())

    def test_lab_with_ticket_cannot_be_deleted(self):
        table = ProblemTable.objects.create(name='Lab deletion check')
        ProblemSample.objects.create(table=table, lab=self.calgary, problem_number=77)
        result = self.client.delete(f'/api/auth/labs/{self.calgary.pk}/')
        self.assertEqual(result.status_code, 409, result.data)
        self.assertIn('Tickets', result.data['references'])

    def test_cascade_template_is_still_a_deletion_reference(self):
        # The template FK is CASCADE; a naive deletion would remove it silently.
        LabEmailTemplate.objects.create(lab=self.calgary, key='customer', subject_template='subject', body_template='body')
        result = self.client.delete(f'/api/auth/labs/{self.calgary.pk}/')
        self.assertEqual(result.status_code, 409, result.data)
        self.assertIn('Email templates', result.data['references'])
        self.assertTrue(LabEmailTemplate.objects.filter(lab=self.calgary).exists())

    def test_non_admin_cannot_manage_labs(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post('/api/auth/labs/', {'name': 'New', 'code': 'NEW'}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/auth/labs/{self.calgary.pk}/', {'name': 'New'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/auth/labs/{self.calgary.pk}/').status_code, 403)

    def test_last_lab_cannot_be_deleted(self):
        self.calgary.delete()  # No references; remove the extra lab.
        UserProfile.objects.filter(user__in=[self.staff, self.admin]).update(lab=None)
        result = self.client.delete(f'/api/auth/labs/{self.edmonton.pk}/')
        self.assertEqual(result.status_code, 409, result.data)
        self.assertTrue(Lab.objects.filter(pk=self.edmonton.pk).exists())

    def test_admin_list_includes_reference_summary(self):
        response = self.client.get('/api/auth/labs/')
        self.assertEqual(response.status_code, 200)
        calgary = next(item for item in response.data if item['code'] == 'CGY')
        self.assertTrue(calgary['can_delete'])
        self.assertEqual(calgary['references'], {})
