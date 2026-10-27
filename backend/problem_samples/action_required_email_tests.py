from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import (
    ProblemSample, ProblemTable, ProblemTrackingLink,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
)


@override_settings(FRONTEND_URL='https://tracker.example.test')
class ActionRequiredUpdateEmailTests(TestCase):
    def setUp(self):
        self.sender = User.objects.create_user(username='sender', email='sender@alsglobal.com')
        self.lab_member = User.objects.create_user(
            username='lab.one@alsglobal.com', email='lab.one@alsglobal.com',
        )
        self.customer_service = User.objects.create_user(
            username='cs.person', email='cs.person@alsglobal.com',
        )
        self.email_less = User.objects.create_user(username='not.ready')
        self.inactive = User.objects.create_user(
            username='inactive', email='inactive@alsglobal.com', is_active=False,
        )
        UserProfile.objects.create(user=self.lab_member, role=UserProfile.ROLE_LAB_TECHNICIAN)
        UserProfile.objects.create(user=self.customer_service, role=UserProfile.ROLE_CUSTOMER_SERVICE)
        self.first = ProblemTable.objects.create(name='Primary', is_default=True)
        self.second = ProblemTable.objects.create(name='Secondary')
        self.client = APIClient()
        self.client.force_authenticate(self.sender)

    def create_ticket(self, table, number, workflow='Follow Up Required'):
        return ProblemSample.objects.create(table=table, problem_number=number, current_workflow=workflow)

    def prepare(self, recipients, message=''):
        return self.client.post('/api/dashboard/action-required-email/', {
            'recipients': recipients, 'message': message,
        }, format='json')

    def test_generates_live_all_table_counts_with_queue_links(self):
        self.create_ticket(self.first, 1)
        self.create_ticket(self.second, 1)
        self.create_ticket(self.second, 2, PROBLEM_STATUS_TO_BE_SHIPPED_BACK)
        self.create_ticket(self.second, 3, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        draft = self.prepare(['@lab.one', '@cs.person'], 'Please check shipping today.')
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(draft.data['counts']['tracking_not_sent'], 2)
        self.assertEqual(draft.data['counts']['to_be_shipped'], 1)
        self.assertEqual(draft.data['counts']['to_be_back_to_testing'], 1)
        self.assertEqual(len(draft.data['counts']), 7)
        self.assertIn('Please check shipping today.', draft.data['body'])
        self.assertIn('https://tracker.example.test/shipping/to-be-shipped', draft.data['body'])
        self.assertIn('https://tracker.example.test/disposal/containers', draft.data['body'])
        self.assertEqual(set(draft.data['recipients']), {
            'lab.one@alsglobal.com', 'cs.person@alsglobal.com'
        })
        self.create_ticket(self.first, 2)
        refreshed = self.prepare(['@cs.person'])
        self.assertEqual(refreshed.data['counts']['tracking_not_sent'], 3)

    def test_lab_group_uses_shared_mailbox_and_deduplicates_individual(self):
        draft = self.prepare(['@Lab', '@lab.one', '@lab.one', '@CustomerService', '@cs.person'])
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(draft.data['recipients'], [
            'NA.EDM@alsglobal.com', 'cs.person@alsglobal.com', 'lab.one@alsglobal.com',
        ])
        self.assertEqual(set(draft.data['mentions']), {
            '@Lab', '@CustomerService', '@lab.one', '@cs.person'
        })

    def test_validates_recipients_and_message(self):
        for recipients in [[], ['somebody@example.com'], ['@missing'], ['@inactive'], ['@not.ready']]:
            with self.subTest(recipients=recipients):
                self.assertEqual(self.prepare(recipients).status_code, 400)
        self.assertEqual(self.prepare(['@Lab'], message='x' * 2001).status_code, 400)
        self.assertEqual(self.prepare(['@Lab'], message='x' * 2000).status_code, 200)

    def test_does_not_send_mail_or_write_history_on_preview(self):
        from django.core import mail
        from .models import ProblemHistory
        start = ProblemHistory.objects.count()
        response = self.prepare(['@Lab'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProblemHistory.objects.count(), start)
        self.assertFalse(getattr(mail, 'outbox', []))

    def test_anonymous_cannot_generate_email(self):
        anonymous = APIClient()
        response = anonymous.post('/api/dashboard/action-required-email/', {
            'recipients': ['@Lab'],
        }, format='json')
        self.assertIn(response.status_code, [401, 403])
