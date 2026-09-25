from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .notification_recipient import DEFAULT_EDMONTON_RECIPIENT, get_edmonton_recipient


class EdmontonRecipientTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='recipient.admin', password='test-password')
        UserProfile.objects.create(user=self.admin, is_admin=True)
        self.staff = User.objects.create_user(username='recipient.staff', password='test-password')
        UserProfile.objects.create(user=self.staff, is_admin=False)
        self.url = '/api/email-templates/edmonton-recipient/'

    def test_staff_can_read_but_cannot_change_shared_address(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.url).data['email'], DEFAULT_EDMONTON_RECIPIENT)
        self.assertEqual(self.client.put(self.url, {'email': 'new@example.com'}, format='json').status_code, 403)
        self.assertEqual(get_edmonton_recipient().email, DEFAULT_EDMONTON_RECIPIENT)

    def test_admin_can_change_address_and_invalid_values_are_rejected(self):
        self.client.force_authenticate(self.admin)
        for email in ('', 'two@example.com;other@example.com', 'not-an-address'):
            self.assertEqual(self.client.put(self.url, {'email': email}, format='json').status_code, 400)
        response = self.client.put(self.url, {'email': ' edm-updates@example.com '}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], 'edm-updates@example.com')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.url).data['email'], 'edm-updates@example.com')
        customer_template = self.client.get('/api/email-templates/customer-notification/')
        self.assertEqual(customer_template.status_code, 200)
        self.assertIn('{{na_edm_email}}', customer_template.data['body_template'])
