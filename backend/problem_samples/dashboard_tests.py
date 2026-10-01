from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT,
    DISPOSE_AUTOMATICALLY_NO,
    PROBLEM_STATUS_DEFAULT,
    PROBLEM_STATUS_SHIPPED_BACK,
    PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
    AutomaticDisposalExpiryEvent,
    ProblemHistory,
    ProblemSample,
    ProblemTable,
    ProblemTrackingLink,
)


class DashboardAnalyticsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dashboard.user', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = ProblemTable.objects.create(name='Dashboard test', is_default=True)

    def make_problem(self, number, created_at):
        problem = ProblemSample.objects.create(
            table=self.table,
            problem_number=number,
            status=PROBLEM_STATUS_DEFAULT,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={
                'status': PROBLEM_STATUS_DEFAULT,
                SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: DISPOSE_AUTOMATICALLY_NO,
            },
        )
        ProblemSample.objects.filter(pk=problem.pk).update(created_at=created_at)
        return problem

    def test_rolling_counts_and_week_chart(self):
        now = timezone.now()
        self.make_problem(1, now - timedelta(hours=2))
        self.make_problem(2, now - timedelta(days=3))
        self.make_problem(3, now - timedelta(days=20))
        self.make_problem(4, now - timedelta(days=200))

        response = self.client.get('/api/dashboard/?range=week')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts']['day'], 1)
        self.assertEqual(response.data['counts']['week'], 2)
        self.assertEqual(response.data['counts']['month'], 3)
        self.assertEqual(response.data['counts']['year'], 4)
        self.assertEqual(response.data['chart']['bucket'], 'day')
        self.assertEqual(response.data['chart']['total'], 2)

    def test_shipping_and_testing_counts_match_queues_across_tables(self):
        now = timezone.now()
        first = self.make_problem(1, now)
        second = self.make_problem(2, now)
        shipped = self.make_problem(3, now)
        self.table = ProblemTable.objects.create(name='Second dashboard table')
        third = self.make_problem(1, now)
        waiting_for_testing = self.make_problem(2, now)
        ProblemSample.objects.filter(pk__in=[first.pk, third.pk]).update(
            current_workflow=PROBLEM_STATUS_TO_BE_SHIPPED_BACK
        )
        ProblemSample.objects.filter(pk__in=[second.pk, waiting_for_testing.pk]).update(
            current_workflow=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING
        )
        ProblemSample.objects.filter(pk=shipped.pk).update(current_workflow=PROBLEM_STATUS_SHIPPED_BACK)

        counts = self.client.get('/api/dashboard/').data['counts']
        shipping = self.client.get('/api/problem-samples/to-be-shipped/')
        testing = self.client.get('/api/problem-samples/to-be-back-to-testing/')
        self.assertEqual(shipping.status_code, 200)
        self.assertEqual(testing.status_code, 200)
        self.assertEqual(counts['to_be_shipped'], 2)
        self.assertEqual(counts['to_be_back_to_testing'], 2)
        self.assertEqual(len(shipping.data), counts['to_be_shipped'])
        self.assertEqual(len(testing.data), counts['to_be_back_to_testing'])

    def test_tracking_emails_sent_today_counts_links_created_on_local_calendar_day(self):
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        today_noon = timezone.make_aware(datetime.combine(today, time(hour=12)), tz)
        yesterday_noon = today_noon - timedelta(days=1)

        first = self.make_problem(10, today_noon)
        second = self.make_problem(11, today_noon)
        old = self.make_problem(12, yesterday_noon)

        first_link = ProblemTrackingLink.objects.create(ticket=first, tracking_token='today-link-1')
        second_link = ProblemTrackingLink.objects.create(ticket=second, tracking_token='today-link-2')
        old_link = ProblemTrackingLink.objects.create(ticket=old, tracking_token='yesterday-link')
        ProblemTrackingLink.objects.filter(pk=first_link.pk).update(date_created=today_noon)
        ProblemTrackingLink.objects.filter(pk=second_link.pk).update(date_created=today_noon)
        ProblemTrackingLink.objects.filter(pk=old_link.pk).update(date_created=yesterday_noon)

        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts']['tracking_emails_today'], 2)


    def test_automatic_disposal_expiry_graph_uses_effective_expiry_time(self):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        today = timezone.localdate(now)
        yesterday = today - timedelta(days=1)
        yesterday_noon = timezone.make_aware(datetime.combine(yesterday, time(hour=12)), tz)
        today_event = now - timedelta(minutes=1)

        first = self.make_problem(20, yesterday_noon)
        second = self.make_problem(21, today_event)
        third = self.make_problem(22, today_event)
        AutomaticDisposalExpiryEvent.objects.create(ticket=first, effective_at=yesterday_noon)
        AutomaticDisposalExpiryEvent.objects.create(ticket=second, effective_at=today_event)
        AutomaticDisposalExpiryEvent.objects.create(ticket=third, effective_at=today_event)

        response = self.client.get('/api/dashboard/?range=week')
        self.assertEqual(response.status_code, 200)
        chart = response.data['automatic_disposal_chart']
        self.assertEqual(chart['bucket'], 'day')
        self.assertEqual(chart['total'], 3)
        counts = {point['period']: point['count'] for point in chart['points']}
        self.assertEqual(counts[yesterday.isoformat()], 1)
        self.assertEqual(counts[today.isoformat()], 2)

    def test_custom_range_is_inclusive(self):
        tz = timezone.get_current_timezone()
        target = timezone.localdate() - timedelta(days=10)
        created = timezone.make_aware(datetime.combine(target, time(hour=12)), tz)
        self.make_problem(1, created)
        response = self.client.get('/api/dashboard/', {
            'range': 'custom',
            'start_date': target.isoformat(),
            'end_date': target.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts']['custom'], 1)
        self.assertEqual(response.data['chart']['total'], 1)

    def test_backwards_custom_range_is_rejected(self):
        today = timezone.localdate()
        response = self.client.get('/api/dashboard/', {
            'range': 'custom',
            'start_date': today.isoformat(),
            'end_date': (today - timedelta(days=1)).isoformat(),
        })
        self.assertEqual(response.status_code, 400)

    def test_customer_responded_uses_latest_person_and_workflow(self):
        other_table = ProblemTable.objects.create(name='Other dashboard table')
        first = self.make_problem(1, timezone.now() - timedelta(days=1))
        second = self.make_problem(2, timezone.now() - timedelta(days=2))
        staff_later = self.make_problem(3, timezone.now() - timedelta(days=3))
        terminal = self.make_problem(4, timezone.now() - timedelta(days=4))
        never_responded = self.make_problem(5, timezone.now() - timedelta(days=5))
        second.table = other_table
        second.current_workflow = 'Waiting for Customer Response'
        second.save(update_fields=['table', 'current_workflow'])
        terminal.current_workflow = 'To be shipped back to client'
        terminal.save(update_fields=['current_workflow'])
        ProblemHistory.objects.create(problem=never_responded, action=ProblemHistory.ACTION_CREATED,
            actor=self.user, summary='Created', details={})

        def customer_change(ticket, label='Hold sample'):
            return ProblemHistory.objects.create(problem=ticket, action=ProblemHistory.ACTION_UPDATED,
                summary=f'Customer selected: {label}',
                details={'responded_via': 'public_tracking_link', 'customer_action_label': label})

        customer_change(first)
        customer_change(first, 'Ship back')
        customer_change(second)
        customer_change(staff_later)
        customer_change(terminal)
        ProblemHistory.objects.create(problem=staff_later, action=ProblemHistory.ACTION_COMMENT,
            actor=self.user, summary='Added comment', details={'comment': 'Followed up'})
        # A system-generated change does not count as the latest person.
        ProblemHistory.objects.create(problem=first, action=ProblemHistory.ACTION_UPDATED,
            summary='Automatic rule applied', details={'automatic': True, 'changes': []})
        # The response stays on the ticket even if acknowledgement fields are reset.
        first.acknowledged_at = None
        first.customer_acknowledgement_action = ''
        first.save(update_fields=['acknowledged_at', 'customer_acknowledgement_action'])

        dashboard = self.client.get('/api/dashboard/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data['counts']['customer_responded'], 2)
        response = self.client.get('/api/dashboard/customer-responded/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual({row['problem_number'] for row in response.data['results']}, {1, 2})
        selected = next(row for row in response.data['results'] if row['problem_number'] == 1)
        self.assertEqual(selected['customer_response'], 'Ship back')
        filtered = self.client.get('/api/dashboard/customer-responded/', {'table': str(other_table.id)})
        self.assertEqual(filtered.data['count'], 1)
        self.assertEqual(filtered.data['results'][0]['problem_number'], 2)

        # A new response brings a ticket back into the view; a staff edit removes it again.
        customer_change(staff_later)
        self.assertEqual(self.client.get('/api/dashboard/').data['counts']['customer_responded'], 3)
        ProblemHistory.objects.create(problem=staff_later, action=ProblemHistory.ACTION_UPDATED,
            actor=self.user, summary='Saved changes', details={'changes': []})
        self.assertEqual(self.client.get('/api/dashboard/').data['counts']['customer_responded'], 2)

    def test_customer_responded_list_requires_authentication(self):
        guest = APIClient()
        self.assertNotEqual(guest.get('/api/dashboard/customer-responded/').status_code, 200)
