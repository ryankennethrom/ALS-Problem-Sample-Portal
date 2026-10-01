from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import ProblemHistory, ProblemSample, ProblemTable, ProblemTrackingLink


class TrackingNotSentDashboardTests(TestCase):
    def test_count_and_queue_agree_across_tables_and_workflows(self):
        client = APIClient()
        client.force_authenticate(User.objects.create_user(username='tracking.dashboard'))
        first = ProblemTable.objects.create(name='First table')
        second = ProblemTable.objects.create(name='Second table')

        def ticket(table, number, workflow='CS Follow-Up'):
            return ProblemSample.objects.create(
                table=table, problem_number=number, current_workflow=workflow,
            )

        ticket(first, 1)
        waiting = ticket(second, 1, 'Waiting for Customer Response')
        with_link = ticket(first, 2)
        ProblemTrackingLink.objects.create(ticket=with_link, tracking_token='persisted-link')
        for number, workflow in enumerate([
            'To be Disposed', 'To be shipped back to client', 'To be back to testing', 'Back to testing',
            'Disposed', 'Shipped back to client',
        ], start=3):
            ticket(first, number, workflow)

        dashboard = client.get('/api/dashboard/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data['counts']['tracking_not_sent'], 1)

        response = client.get('/api/problem-samples/follow-up-required/', {
            'table': str(first.pk), 'tracking_not_sent': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

        waiting_response = client.get('/api/problem-samples/follow-up-required/', {
            'table': str(second.pk), 'tracking_not_sent': '1',
        })
        self.assertEqual(waiting_response.status_code, 200)
        self.assertEqual(len(waiting_response.data), 0)

        all_rows = client.get('/api/problem-samples/follow-up-required/', {'table': str(first.pk)})
        self.assertEqual(len(all_rows.data), 2)
        filtered = client.post('/api/problem-samples/follow-up-required/', {
            'table': str(first.pk), 'tracking_not_sent': '1',
            'filters': [], 'quick_filters': [], 'match': 'all',
        }, format='json')
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.data), 1)

        with_link.tracking_link_record.delete()
        self.assertEqual(client.get('/api/dashboard/').data['counts']['tracking_not_sent'], 2)

        waiting.set_workflow_status('CS Follow-Up')
        waiting.save(update_fields=['current_workflow', 'custom_values'])
        self.assertEqual(client.get('/api/dashboard/').data['counts']['tracking_not_sent'], 3)


class CustomerServiceOtherQueueTests(TestCase):
    def test_other_is_cs_follow_up_minus_tracking_not_sent_and_new_response(self):
        client = APIClient()
        user = User.objects.create_user(username='customer.service.other')
        client.force_authenticate(user)
        table = ProblemTable.objects.create(name='Customer Service queues')

        tracking_not_sent = ProblemSample.objects.create(
            table=table, problem_number=1, current_workflow='CS Follow-Up',
        )
        new_response = ProblemSample.objects.create(
            table=table, problem_number=2, current_workflow='CS Follow-Up',
        )
        other = ProblemSample.objects.create(
            table=table, problem_number=3, current_workflow='CS Follow-Up',
        )
        waiting = ProblemSample.objects.create(
            table=table, problem_number=4, current_workflow='Waiting for Customer Response',
        )

        ProblemTrackingLink.objects.create(ticket=new_response, tracking_token='response-link')
        ProblemTrackingLink.objects.create(ticket=other, tracking_token='other-link')
        ProblemTrackingLink.objects.create(ticket=waiting, tracking_token='waiting-link')
        ProblemHistory.objects.create(
            problem=new_response, action=ProblemHistory.ACTION_UPDATED,
            summary='Customer selected: Give us more details',
            details={'responded_via': 'public_tracking_link', 'customer_action_label': 'Give us more details'},
        )
        ProblemHistory.objects.create(
            problem=other, action=ProblemHistory.ACTION_COMMENT, actor=user,
            summary='Added comment', details={'comment': 'Staff follow-up'},
        )

        response = client.get('/api/problem-samples/follow-up-required/', {
            'table': str(table.pk), 'other': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['problem_number'] for row in response.data], [3])

        tracking_response = client.get('/api/problem-samples/follow-up-required/', {
            'table': str(table.pk), 'tracking_not_sent': '1',
        })
        self.assertEqual([row['problem_number'] for row in tracking_response.data], [1])

        responded = client.get('/api/dashboard/customer-responded/', {'table': str(table.pk)})
        self.assertEqual([row['problem_number'] for row in responded.data['results']], [2])

        invalid = client.get('/api/problem-samples/follow-up-required/', {
            'table': str(table.pk), 'tracking_not_sent': '1', 'other': '1',
        })
        self.assertEqual(invalid.status_code, 400)
