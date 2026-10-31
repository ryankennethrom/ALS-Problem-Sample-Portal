"""Role-limited staff viewing of tracking URLs, without breaking email preparation."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Lab, UserProfile
from .models import ProblemSample, ProblemTable, ProblemTrackingLink, ProblemHistory, generate_acknowledgement_token
from .serializers import ShippingProblemSampleSerializer


class TrackingLinkAdminVisibilityTests(TestCase):
    def setUp(self):
        lab = Lab.objects.get(code='EDM')
        self.table = ProblemTable.objects.create(name='Link permission test')
        self.staff = User.objects.create_user(username='link-staff')
        UserProfile.objects.create(user=self.staff, role='lab_technician', lab=lab, is_admin=False)
        self.admin = User.objects.create_user(username='link-admin')
        UserProfile.objects.create(user=self.admin, role='lab_technician', lab=lab, is_admin=True)
        self.ticket = ProblemSample.objects.create(table=self.table, lab=lab, problem_number=1)
        self.token = generate_acknowledgement_token()
        ProblemTrackingLink.objects.create(ticket=self.ticket, tracking_token=self.token)
        self.client = APIClient()
        self.url = f'/api/problem-samples/{self.ticket.pk}/'

    def test_staff_can_read_tracking_url_but_not_raw_token_from_ticket_detail(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.url, HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.token, response.data['tracking_url'])
        self.assertIn(self.token, response.data['acknowledgement_url'])
        self.assertIsNone(response.data['acknowledgement_token'])
        self.assertNotIn('pending_tracking_token', response.data)
        self.assertIn(self.token, str(response.data))

    def test_staff_can_read_tracking_url_from_ticket_list(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get('/api/problem-samples/', HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data if isinstance(response.data, list) else response.data['results']
        entry = next(row for row in rows if row['id'] == str(self.ticket.pk))
        self.assertIn(self.token, entry['tracking_url'])
        self.assertIn(self.token, str(entry))

    def test_staff_can_read_tracking_url_in_queue_serializer(self):
        from types import SimpleNamespace
        data = ShippingProblemSampleSerializer(self.ticket, context={'request': SimpleNamespace(user=self.staff)}).data
        self.assertIn(self.token, data['tracking_url'])
        admin_data = ShippingProblemSampleSerializer(self.ticket, context={'request': SimpleNamespace(user=self.admin)}).data
        self.assertIn(self.token, admin_data['tracking_url'])

    def test_admin_can_read_tracking_link_and_token(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url, HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.token, response.data['tracking_url'])
        self.assertEqual(response.data['acknowledgement_token'], self.token)
        self.assertNotIn('pending_tracking_token', response.data)

    def test_staff_can_still_prepare_customer_tracking_email(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(self.url + 'customer-notification-credentials/', {}, format='json', HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.token, response.data['tracking_url'])

    def test_staff_history_preserves_urls_for_read_only_display(self):
        url = f'https://tracker.example/track/{self.token}?message=1'
        entry = ProblemHistory.objects.create(
            problem=self.ticket, action=ProblemHistory.ACTION_CUSTOMER_NOTIFICATION,
            summary='Replied to customer message',
            details={'tracking_url': url, 'notes': ['Customer link: ' + url], 'other': 'Unrelated notes'},
        )
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.url, HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(response.status_code, 200, response.data)
        history = next(item for item in response.data['history'] if item['id'] == entry.pk)
        self.assertEqual(history['details']['tracking_url'], url)
        self.assertIn('Unrelated notes', str(history['details']))
        self.client.force_authenticate(self.admin)
        admin_response = self.client.get(self.url, HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(admin_response.status_code, 200, admin_response.data)
        admin_entry = next(item for item in admin_response.data['history'] if item['id'] == entry.pk)
        self.assertEqual(admin_entry['details']['tracking_url'], url)
