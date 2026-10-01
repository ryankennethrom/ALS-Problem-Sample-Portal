from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from .models import Customer, CustomerImport


class CustomerAdminAccessTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin.user', password='test-password')
        UserProfile.objects.create(user=self.admin, is_admin=True)
        self.user = User.objects.create_user(username='regular.user', password='test-password')
        UserProfile.objects.create(user=self.user, role=UserProfile.ROLE_LAB_TECHNICIAN)
        Customer.objects.create(company_name='Example Customer', email='customer@example.com')

    def test_non_admin_cannot_open_customer_directory_or_overview(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get('/api/customers/').status_code, 403)
        self.assertEqual(self.client.get('/api/customers/overview/').status_code, 403)

    def test_non_admin_cannot_import_customer_export(self):
        self.client.force_authenticate(user=self.user)
        upload = SimpleUploadedFile(
            'customers.csv',
            b'CoyId,Company,Email\n1,New Customer,new@example.com\n',
            content_type='text/csv',
        )
        self.assertEqual(self.client.post('/api/customers/import/', {'file': upload}, format='multipart').status_code, 403)

    def test_non_admin_can_still_use_form_suggestion_endpoints(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get('/api/customers/distributors/suggest/?q=test').status_code, 200)
        self.assertEqual(self.client.get('/api/customers/end-users/suggest/?q=test').status_code, 200)
        self.assertEqual(self.client.get('/api/customers/brands/suggest/?q=test').status_code, 200)


class CustomerImportHistoryTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin.user',
            first_name='Admin',
            last_name='User',
            password='test-password',
        )
        UserProfile.objects.create(user=self.admin, is_admin=True)
        self.client.force_authenticate(user=self.admin)

    def upload(self, filename, rows):
        content = 'CoyId,Company,Email\n' + ''.join(
            f'{customer_id},{company},{email}\n' for customer_id, company, email in rows
        )
        upload = SimpleUploadedFile(filename, content.encode('utf-8'), content_type='text/csv')
        return self.client.post('/api/customers/import/', {'file': upload}, format='multipart')

    def test_import_history_is_retained_and_overview_counts_current_rows(self):
        first = self.upload('first.csv', [('1', 'First Customer', 'first@example.com')])
        self.assertEqual(first.status_code, 201)
        second = self.upload(
            'second.csv',
            [
                ('2', 'Second Customer', 'second@example.com'),
                ('3', 'Third Customer', 'third@example.com'),
            ],
        )
        self.assertEqual(second.status_code, 201)

        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(CustomerImport.objects.count(), 2)

        overview = self.client.get('/api/customers/overview/')
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.data['row_count'], 2)
        self.assertEqual(overview.data['history_count'], 2)
        self.assertEqual(overview.data['latest_upload']['filename'], 'second.csv')
        self.assertEqual(overview.data['latest_upload']['row_count'], 2)
        self.assertEqual(overview.data['latest_upload']['uploaded_by']['name'], 'Admin User')
        self.assertEqual(overview.data['history'][1]['filename'], 'first.csv')
