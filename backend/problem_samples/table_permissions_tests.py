from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import ProblemColumn, ProblemTable


class ManageTablesPermissionsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username='staff', password='test-password')
        self.admin_user = User.objects.create_user(username='admin', password='test-password')
        UserProfile.objects.create(user=self.staff_user, is_admin=False)
        UserProfile.objects.create(user=self.admin_user, is_admin=True)
        self.staff = APIClient()
        self.staff.force_authenticate(self.staff_user)
        self.admin = APIClient()
        self.admin.force_authenticate(self.admin_user)
        self.table = ProblemTable.objects.create(name='Existing table', is_default=True)
        self.column = ProblemColumn.objects.create(
            table=self.table, name='Existing column', field_key='existing-column', column_type='text',
        )
        self.table_url = '/api/problem-tables/'
        self.column_url = '/api/problem-columns/'

    def test_staff_can_read_table_definitions_but_cannot_manage_them(self):
        self.assertEqual(self.staff.get(self.table_url).status_code, 200)
        self.assertEqual(self.staff.get(f'{self.table_url}{self.table.id}/').status_code, 200)
        self.assertEqual(self.staff.get(self.column_url).status_code, 200)
        self.assertEqual(self.staff.get(f'{self.column_url}{self.column.id}/').status_code, 200)
        for response in (
            self.staff.post(self.table_url, {'name': 'Unauthorized'}, format='json'),
            self.staff.patch(f'{self.table_url}{self.table.id}/', {'name': 'Unauthorized'}, format='json'),
            self.staff.delete(f'{self.table_url}{self.table.id}/'),
            self.staff.post(f'{self.table_url}{self.table.id}/status-values/', {}, format='json'),
            self.staff.post(self.column_url, {'table': str(self.table.id), 'name': 'Unauthorized'}, format='json'),
            self.staff.patch(f'{self.column_url}{self.column.id}/', {'name': 'Unauthorized'}, format='json'),
            self.staff.delete(f'{self.column_url}{self.column.id}/'),
        ):
            self.assertEqual(response.status_code, 403)
        self.table.refresh_from_db()
        self.column.refresh_from_db()
        self.assertEqual(self.table.name, 'Existing table')
        self.assertEqual(self.column.name, 'Existing column')

    def test_admin_can_manage_tables_and_columns(self):
        self.assertEqual(self.admin.patch(f'{self.table_url}{self.table.id}/', {'name': 'Renamed'}, format='json').status_code, 200)
        self.assertEqual(self.admin.patch(f'{self.column_url}{self.column.id}/', {'name': 'Renamed column'}, format='json').status_code, 200)
        self.table.refresh_from_db()
        self.column.refresh_from_db()
        self.assertEqual(self.table.name, 'Renamed')
        self.assertEqual(self.column.name, 'Renamed column')

    def test_unauthenticated_cannot_read_table_definitions(self):
        self.assertNotEqual(APIClient().get(self.table_url).status_code, 200)
