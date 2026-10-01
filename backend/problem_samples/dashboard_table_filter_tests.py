from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ProblemSample, ProblemTable, PROBLEM_STATUS_TO_BE_SHIPPED_BACK


class DashboardTableFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='dashboard.table@alsglobal.com',
            email='dashboard.table@alsglobal.com',
            password='test-password',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.first = ProblemTable.objects.create(name='First table', is_default=True)
        self.second = ProblemTable.objects.create(name='Second table')

    def ticket(self, table, number, age_days, workflow='CS Follow-Up'):
        row = ProblemSample.objects.create(
            table=table,
            problem_number=number,
            current_workflow=workflow,
            custom_values={'system-current-workflow': workflow},
        )
        ProblemSample.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=age_days))
        row.refresh_from_db()
        return row

    def test_opened_counts_and_chart_are_scoped_to_selected_table(self):
        self.ticket(self.first, 1, 1)
        self.ticket(self.first, 2, 20)
        self.ticket(self.second, 1, 2)
        self.ticket(self.second, 2, 3, PROBLEM_STATUS_TO_BE_SHIPPED_BACK)

        response = self.client.get('/api/dashboard/', {'range': 'week', 'table': str(self.first.id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['selected_table']['id'], str(self.first.id))
        self.assertEqual(response.data['counts']['week'], 1)
        self.assertEqual(response.data['counts']['month'], 2)
        self.assertEqual(response.data['chart']['total'], 1)
        # Action Required remains an all-table operational count.
        self.assertEqual(response.data['counts']['to_be_shipped'], 1)

    def test_problem_table_opened_range_matches_dashboard_card(self):
        wanted = self.ticket(self.first, 1, 2)
        self.ticket(self.first, 2, 10)
        self.ticket(self.second, 1, 1)

        response = self.client.get('/api/problem-samples/', {
            'table': str(self.first.id),
            'opened_range': 'week',
        })
        self.assertEqual(response.status_code, 200)
        rows = response.data if isinstance(response.data, list) else response.data['results']
        self.assertEqual([str(row['id']) for row in rows], [str(wanted.id)])
