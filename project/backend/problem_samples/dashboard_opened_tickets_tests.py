from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ProblemSample, ProblemTable


class DashboardOpenedTicketsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='dashboard.samples')
        self.client.force_authenticate(self.user)
        self.first_table = ProblemTable.objects.create(name='First table', is_default=True)
        self.second_table = ProblemTable.objects.create(name='Second table')

    def make_ticket(self, table, number, created_at):
        ticket = ProblemSample.objects.create(table=table, problem_number=number)
        ProblemSample.objects.filter(pk=ticket.pk).update(created_at=created_at)
        ticket.refresh_from_db()
        return ticket

    def test_week_list_matches_rolling_window_across_tables(self):
        now = timezone.now()
        first = self.make_ticket(self.first_table, 1, now - timedelta(days=1))
        second = self.make_ticket(self.second_table, 1, now - timedelta(days=6))
        self.make_ticket(self.first_table, 2, now - timedelta(days=8))

        response = self.client.get('/api/dashboard/opened-tickets/', {'range': 'week'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual({row['id'] for row in response.data['results']}, {str(first.pk), str(second.pk)})
        self.assertEqual({row['table_name'] for row in response.data['results']}, {'First table', 'Second table'})

    def test_custom_range_uses_inclusive_calendar_dates(self):
        tz = timezone.get_current_timezone()
        target = timezone.localdate() - timedelta(days=20)
        in_range = timezone.make_aware(datetime.combine(target, time(hour=15)), tz)
        before = timezone.make_aware(datetime.combine(target - timedelta(days=1), time(hour=23)), tz)
        after = timezone.make_aware(datetime.combine(target + timedelta(days=1), time.min), tz)
        wanted = self.make_ticket(self.first_table, 10, in_range)
        self.make_ticket(self.first_table, 11, before)
        self.make_ticket(self.first_table, 12, after)

        response = self.client.get('/api/dashboard/opened-tickets/', {
            'range': 'custom',
            'start_date': target.isoformat(),
            'end_date': target.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(wanted.pk))

    def test_custom_range_requires_both_dates(self):
        response = self.client.get('/api/dashboard/opened-tickets/', {
            'range': 'custom',
            'start_date': timezone.localdate().isoformat(),
        })
        self.assertEqual(response.status_code, 400)

    def test_list_requires_authentication(self):
        guest = APIClient()
        self.assertNotEqual(guest.get('/api/dashboard/opened-tickets/', {'range': 'week'}).status_code, 200)
