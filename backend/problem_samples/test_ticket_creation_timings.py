"""Regression coverage for accurate staff time tracking on successful creation."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import TicketCreationTiming, ProblemSample, PreparedProblemSample
from .views import get_default_table


class TicketCreationTimingTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff-time', email='staff-time@alsglobal.com')
        self.admin = User.objects.create_user(username='admin-time', email='admin-time@alsglobal.com')
        UserProfile.objects.create(user=self.staff, role=UserProfile.ROLE_LAB_TECHNICIAN)
        UserProfile.objects.create(user=self.admin, role=UserProfile.ROLE_LAB_TECHNICIAN, is_admin=True)
        self.api = APIClient()
        self.api.force_authenticate(self.staff)
        self.table = get_default_table()

    def start(self):
        res = self.api.post('/api/ticket-creation-timing/start/', {}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return res.data['id']

    def prepare(self):
        res = self.api.post('/api/problem-samples/prepare-new/', {
            'table': str(self.table.pk), 'custom_values': {},
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return res.data['id']

    def finish(self, draft, timing_id, sent=False):
        return self.api.post('/api/problem-samples/create-prepared/', {
            'id': draft, 'sent': sent, 'creation_timing_id': timing_id,
            **({'not_sent_reason': 'No contact email'} if not sent else {}),
        }, format='json')

    def admin_report(self):
        self.api.force_authenticate(self.admin)
        return self.api.get('/api/admin/ticket-creation-time/')

    def test_click_alone_never_counts_and_staff_cannot_view_report(self):
        self.start()
        self.assertEqual(TicketCreationTiming.objects.filter(completed_at__isnull=False).count(), 0)
        self.assertEqual(self.api.get('/api/admin/ticket-creation-time/').status_code, 403)
        response = self.admin_report()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['tickets'], 0)

    def test_canceled_preparation_is_not_counted(self):
        timing_id = self.start()
        draft = self.prepare()
        self.assertEqual(self.api.post('/api/problem-samples/cancel-prepared/', {'id': draft}, format='json').status_code, 204)
        record = TicketCreationTiming.objects.get(pk=timing_id)
        self.assertIsNone(record.completed_at)
        self.assertEqual(self.admin_report().data['summary']['tickets'], 0)

    def test_failed_finalization_is_not_counted(self):
        timing_id = self.start()
        draft = self.prepare()
        result = self.api.post('/api/problem-samples/create-prepared/', {
            'id': draft, 'sent': 'invalid', 'creation_timing_id': timing_id,
        }, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertFalse(TicketCreationTiming.objects.get(pk=timing_id).completed_at)
        self.assertEqual(ProblemSample.objects.count(), 0)

    def test_final_confirmation_counts_exactly_one_record(self):
        timing_id = self.start()
        start = timezone.now() - timedelta(minutes=3, seconds=20)
        TicketCreationTiming.objects.filter(pk=timing_id).update(started_at=start)
        draft = self.prepare()
        completed = self.finish(draft, timing_id)
        self.assertEqual(completed.status_code, 201, completed.data)
        record = TicketCreationTiming.objects.get(pk=timing_id)
        self.assertIsNotNone(record.completed_at)
        self.assertEqual(str(record.completed_ticket_id), completed.data['id'])
        self.assertFalse(record.email_sent)
        self.assertGreaterEqual(record.duration_ms, 195000)
        again = self.finish(draft, timing_id)
        self.assertEqual(again.data['id'], completed.data['id'])
        self.assertEqual(TicketCreationTiming.objects.filter(completed_at__isnull=False).count(), 1)
        result = self.admin_report()
        self.assertEqual(result.data['summary']['tickets'], 1)
        self.assertEqual(result.data['staff'][0]['staff_name'], 'staff-time@alsglobal.com')
        self.assertEqual(result.data['staff'][0]['tickets'], 1)
        self.assertEqual(result.data['daily'][0]['staff'][0]['tickets'], 1)

    def test_sent_email_also_counts(self):
        timing_id = self.start()
        completed = self.finish(self.prepare(), timing_id, sent=True)
        self.assertEqual(completed.status_code, 201, completed.data)
        self.assertTrue(TicketCreationTiming.objects.get(pk=timing_id).email_sent)

    def test_other_staff_cannot_use_attempt(self):
        timing_id = self.start()
        draft = self.prepare()
        other = User.objects.create_user(username='second-staff')
        other_client = APIClient()
        other_client.force_authenticate(other)
        second_timing = other_client.post('/api/ticket-creation-timing/start/', {}, format='json').data['id']
        denied = self.finish(draft, second_timing)
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(ProblemSample.objects.count(), 0)
        completed = self.finish(draft, timing_id)
        self.assertEqual(completed.status_code, 201, completed.data)

    def test_invalid_range_is_rejected(self):
        self.api.force_authenticate(self.admin)
        r = self.api.get('/api/admin/ticket-creation-time/?start_date=bad&end_date=2026-10-21')
        self.assertEqual(r.status_code, 400)
        r = self.api.get('/api/admin/ticket-creation-time/?start_date=2026-10-22&end_date=2026-10-21')
        self.assertEqual(r.status_code, 400)

    def test_history_stays_after_ticket_deleted(self):
        timing_id = self.start()
        response = self.finish(self.prepare(), timing_id)
        self.assertEqual(response.status_code, 201)
        ProblemSample.objects.get(pk=response.data['id']).delete()
        record = TicketCreationTiming.objects.get(pk=timing_id)
        self.assertIsNone(record.completed_ticket_id)
        self.assertIsNotNone(record.completed_at)
        self.assertEqual(self.admin_report().data['summary']['tickets'], 1)
