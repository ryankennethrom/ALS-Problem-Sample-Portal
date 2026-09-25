from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import ProblemSample, ProblemTable, ProblemTrackingLink


class TrackingNotSentDashboardTests(TestCase):
    def test_count_and_queue_agree_across_tables_and_workflows(self):
        client = APIClient()
        client.force_authenticate(User.objects.create_user(username='tracking.dashboard'))
        first = ProblemTable.objects.create(name='First table')
        second = ProblemTable.objects.create(name='Second table')

        def ticket(table, number, workflow='CS Follow-Up', status='NEW'):
            return ProblemSample.objects.create(
                table=table, problem_number=number, current_workflow=workflow, status=status,
            )

        ticket(first, 1)
        ticket(second, 1, 'Waiting For Customer', 'IN PROGRESS')
        with_link = ticket(first, 2)
        ProblemTrackingLink.objects.create(ticket=with_link, tracking_token='persisted-link')
        for number, workflow in enumerate([
            'To be Disposed', 'To be shipped back to client', 'To be back to testing', 'Back to testing',
            'Disposed', 'Shipped back to client',
        ], start=3):
            ticket(first, number, workflow)

        dashboard = client.get('/api/dashboard/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data['counts']['tracking_not_sent'], 2)

        for table in (first, second):
            response = client.get('/api/problem-samples/follow-up-required/', {
                'table': str(table.pk), 'tracking_not_sent': '1',
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data), 1)

        all_rows = client.get('/api/problem-samples/follow-up-required/', {'table': str(first.pk)})
        self.assertEqual(len(all_rows.data), 2)
        filtered = client.post('/api/problem-samples/follow-up-required/', {
            'table': str(first.pk), 'tracking_not_sent': '1',
            'filters': [], 'quick_filters': [], 'match': 'all',
        }, format='json')
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.data), 1)

        with_link.tracking_link_record.delete()
        self.assertEqual(client.get('/api/dashboard/').data['counts']['tracking_not_sent'], 3)
