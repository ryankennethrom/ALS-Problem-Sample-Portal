from datetime import datetime, time, timedelta
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import ProblemSample, ProblemTable, ProblemTrackingLink
from .terminal_cleanup_views import _default_end_date
from .old_tickets import old_ticket_anniversary, old_ticket_end_date


URL = '/api/admin/terminal-ticket-cleanup/'
SETTING_URL = '/api/admin/old-ticket-definition/'


class TerminalTicketCleanupTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='cleanup.admin')
        UserProfile.objects.create(user=self.admin, is_admin=True)
        self.staff = User.objects.create_user(username='cleanup.staff')
        UserProfile.objects.create(user=self.staff, is_admin=False)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.table = ProblemTable.objects.create(name='Cleanup test')

    def ticket(self, number, day, workflow):
        row = ProblemSample.objects.create(
            table=self.table, problem_number=number, current_workflow=workflow,
        )
        created = timezone.make_aware(datetime.combine(day, time(hour=12)), timezone.get_current_timezone())
        ProblemSample.objects.filter(pk=row.pk).update(created_at=created)
        return row

    def delete_preview(self, preview):
        return self.client.post(URL, {
            'start_date': preview['start_date'],
            'end_date': preview['end_date'],
            'expected_count': preview['count'],
            'fingerprint': preview['fingerprint'],
            'confirmation': f"DELETE {preview['count']}",
        }, format='json')

    def test_default_includes_only_finished_workflows_at_least_two_years_old(self):
        cutoff = _default_end_date()
        disposed = self.ticket(1, cutoff, 'Disposed')
        shipped = self.ticket(2, cutoff - timedelta(days=1), 'Shipped back to client')
        back_to_testing = self.ticket(3, cutoff - timedelta(days=2), 'Back to testing')
        link = ProblemTrackingLink.objects.create(ticket=disposed, tracking_token='delete-link')
        unfinished = [
            self.ticket(4, cutoff, 'To be Disposed'),
            self.ticket(5, cutoff, 'To be shipped back to client'),
            self.ticket(6, cutoff, 'To be back to testing'),
            self.ticket(7, cutoff, 'CS Follow-Up'),
        ]
        newer = self.ticket(8, cutoff + timedelta(days=1), 'Disposed')

        preview_response = self.client.get(URL)
        self.assertEqual(preview_response.status_code, 200)
        preview = preview_response.data
        self.assertEqual(preview['end_date'], cutoff.isoformat())
        self.assertEqual(preview['count'], 3)
        self.assertEqual(preview['by_workflow'], {
            'Disposed': 1,
            'Shipped back to client': 1,
            'Back to testing': 1,
        })
        self.assertTrue(ProblemTrackingLink.objects.filter(pk=link.pk).exists())

        deleted = self.delete_preview(preview)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.data['deleted_tickets'], 3)
        self.assertFalse(ProblemSample.objects.filter(pk__in=[disposed.pk, shipped.pk, back_to_testing.pk]).exists())
        self.assertFalse(ProblemTrackingLink.objects.filter(pk=link.pk).exists())
        self.assertEqual(ProblemSample.objects.filter(pk__in=[row.pk for row in unfinished] + [newer.pk]).count(), 5)

    def test_custom_range_is_inclusive_and_preview_must_still_match(self):
        cutoff = _default_end_date()
        before = self.ticket(1, cutoff - timedelta(days=2), 'Disposed')
        selected = self.ticket(2, cutoff - timedelta(days=1), 'Disposed')
        after = self.ticket(3, cutoff, 'Disposed')
        params = {'start_date': (cutoff - timedelta(days=1)).isoformat(), 'end_date': (cutoff - timedelta(days=1)).isoformat()}
        preview = self.client.get(URL, params).data
        self.assertEqual(preview['count'], 1)
        self.ticket(4, cutoff - timedelta(days=1), 'Disposed')
        stale = self.delete_preview(preview)
        self.assertEqual(stale.status_code, 409)
        self.assertTrue(ProblemSample.objects.filter(pk=selected.pk).exists())

        updated = self.client.get(URL, params).data
        self.assertEqual(updated['count'], 2)
        self.assertEqual(self.delete_preview(updated).status_code, 200)
        self.assertEqual(ProblemSample.objects.filter(pk__in=[before.pk, after.pk]).count(), 2)

    def test_admin_permission_and_confirmation_are_enforced(self):
        cutoff = _default_end_date()
        row = self.ticket(1, cutoff, 'Disposed')
        preview = self.client.get(URL).data
        payload = {
            'end_date': preview['end_date'], 'expected_count': preview['count'],
            'fingerprint': preview['fingerprint'], 'confirmation': 'DELETE 1',
        }
        staff = APIClient()
        staff.force_authenticate(self.staff)
        self.assertEqual(staff.get(URL).status_code, 403)
        self.assertEqual(staff.post(URL, payload, format='json').status_code, 403)
        guest = APIClient()
        self.assertNotEqual(guest.post(URL, payload, format='json').status_code, 200)
        payload['confirmation'] = 'delete 1'
        self.assertEqual(self.client.post(URL, payload, format='json').status_code, 400)
        self.assertEqual(self.client.post(URL, {'end_date': preview['end_date']}, format='json').status_code, 400)
        self.assertTrue(ProblemSample.objects.filter(pk=row.pk).exists())

    def test_admin_defined_age_updates_dashboard_and_cleanup_default(self):
        default = self.client.get(SETTING_URL)
        self.assertEqual(default.status_code, 200)
        self.assertEqual(default.data['age_months'], 24)
        self.assertEqual(self.client.get(URL).data['end_date'], old_ticket_end_date(24).isoformat())

        changed = self.client.put(SETTING_URL, {'age_months': 18}, format='json')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data['default_end_date'], old_ticket_end_date(18).isoformat())
        old_day = old_ticket_end_date(18)
        self.ticket(1, old_day, 'Disposed')
        self.ticket(2, old_day, 'CS Follow-Up')
        self.ticket(3, old_day + timedelta(days=1), 'Disposed')
        dashboard = self.client.get('/api/dashboard/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data['counts']['old_tickets'], 2)
        self.assertEqual(dashboard.data['old_ticket_definition'], {
            'age_months': 18, 'created_before': old_ticket_anniversary(18).isoformat(),
        })
        preview = self.client.get(URL).data
        self.assertEqual(preview['end_date'], old_day.isoformat())
        self.assertEqual(preview['count'], 1)

        staff = APIClient()
        staff.force_authenticate(self.staff)
        self.assertEqual(staff.get(SETTING_URL).status_code, 403)
        self.assertEqual(staff.put(SETTING_URL, {'age_months': 6}, format='json').status_code, 403)
        for value in (0, 1201, 1.5, '12', True):
            self.assertEqual(self.client.put(SETTING_URL, {'age_months': value}, format='json').status_code, 400)
        self.assertEqual(self.client.get(SETTING_URL).data['age_months'], 18)

    def test_calendar_months_clamp_to_last_day_of_shorter_month(self):
        self.assertEqual(old_ticket_anniversary(1, date(2025, 3, 31)), date(2025, 2, 28))
        self.assertEqual(old_ticket_end_date(1, date(2025, 3, 31)), date(2025, 2, 27))
