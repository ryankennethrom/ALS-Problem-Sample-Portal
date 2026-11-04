"""Django/DB integration tests; run with python manage.py test problem_samples.resend_tracking_links_tests."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import Lab, UserProfile
from .models import ProblemColumn, ProblemHistory, ProblemSample, ProblemTable, CURRENT_WORKFLOW_DEFAULT


class ResendTrackingLinksQueueTests(TestCase):
    def setUp(self):
        self.edm = Lab.objects.create(name='Edmonton Test', code='EDM')
        self.yyc = Lab.objects.create(name='Calgary Test', code='YYC')
        self.user = User.objects.create_user(username='resend.worker')
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.lab = self.edm
        profile.role = UserProfile.ROLE_LAB_TECHNICIAN
        profile.save()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = ProblemTable.objects.create(name='Escalation Test')
        self.column = ProblemColumn.objects.create(
            table=self.table, name='Client Email', field_key='client-email',
            column_type=ProblemColumn.TYPE_CLIENT_EMAIL, client_email_fallback_hours=72,
        )

    def ticket(self, number, lab=None, workflow=CURRENT_WORKFLOW_DEFAULT):
        return ProblemSample.objects.create(table=self.table, lab=lab or self.edm,
                                           problem_number=number, current_workflow=workflow)

    def escalated(self, ticket, reason=None):
        reason = reason or ('End User has not responded for a while. '
                            'The client contact email field has been changed to '
                            'Distributor. Please resend the tracking link.')
        return ProblemHistory.objects.create(problem=ticket, action=ProblemHistory.ACTION_UPDATED,
            summary='Client Email priority escalated; resend tracking link',
            details={'automatic':True, 'reason':reason, 'from_priority':1, 'to_priority':2})

    def get_queue(self):
        return self.client.get('/api/dashboard/resend-tracking-links/')

    def test_queue_requires_latest_history_to_be_the_escalation(self):
        visible = self.ticket(1)
        self.escalated(visible)
        followed_up = self.ticket(2)
        self.escalated(followed_up)
        ProblemHistory.objects.create(problem=followed_up, action=ProblemHistory.ACTION_COMMENT,
                                      summary='Staff follow-up', details={'comment':'Contacted customer'})
        unrelated = self.ticket(3)
        ProblemHistory.objects.create(problem=unrelated, action=ProblemHistory.ACTION_UPDATED,
                                      summary='Other update', details={'reason':'Please resend the tracking link.'})
        waiting = self.ticket(4, workflow='Waiting for Customer Response')
        self.escalated(waiting)
        response = self.get_queue()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['enabled'])
        self.assertEqual([row['problem_number'] for row in response.data['results']], [1])
        self.assertIn('Please resend', response.data['results'][0]['reason'])
        self.assertEqual(self.client.get('/api/dashboard/').data['counts']['resend_tracking_links'], 1)

    def test_legacy_reason_stays_eligible_and_displays_just_field_names(self):
        ticket = self.ticket(17)
        old_reason = ('[Dependency Field Priority 1 — End User] has not responded for a while. '
                      'The client contact email field has been changed to '
                      '[Dependency Field Priority 2 — Distributor]. Please resend the tracking link.')
        history = self.escalated(ticket, reason=old_reason)
        result = self.get_queue()
        self.assertEqual(result.data['count'], 1)
        self.assertEqual(result.data['results'][0]['reason'],
                         'End User has not responded for a while. '
                         'The client contact email field has been changed to '
                         'Distributor. Please resend the tracking link.')
        history.refresh_from_db()
        self.assertEqual(history.details['reason'], old_reason)

    def test_queue_respects_lab(self):
        self.escalated(self.ticket(1, self.edm))
        self.escalated(self.ticket(2, self.yyc))
        self.assertEqual(self.get_queue().data['count'], 1)

    def test_disabled_feature_removes_queue_and_card(self):
        self.escalated(self.ticket(1))
        self.column.client_email_fallback_hours = None
        self.column.save(update_fields=['client_email_fallback_hours'])
        self.assertFalse(self.get_queue().data['enabled'])
        self.assertEqual(self.get_queue().data['count'], 0)
        self.assertFalse(self.client.get('/api/dashboard/').data['resend_tracking_links_enabled'])

    def test_unauthenticated_requests_do_not_expose_tickets(self):
        self.escalated(self.ticket(1))
        self.client.force_authenticate(user=None)
        self.assertIn(self.get_queue().status_code, (401, 403))

    def test_ticket_leaves_queue_after_resend_or_workflow_change(self):
        ticket = self.ticket(1)
        self.escalated(ticket)
        self.assertEqual(self.get_queue().data['count'], 1)
        ProblemHistory.objects.create(problem=ticket, action=ProblemHistory.ACTION_CUSTOMER_NOTIFICATION,
                                      summary='Tracking link resent', details={})
        self.assertEqual(self.get_queue().data['count'], 0)
        self.escalated(ticket)
        ticket.current_workflow = 'Waiting for Customer Response'
        ticket.save(update_fields=['current_workflow'])
        self.assertEqual(self.get_queue().data['count'], 0)

    def test_ordinary_follow_up_queue_does_not_duplicate_resends(self):
        from .models import ProblemTrackingLink
        ticket = self.ticket(1)
        ProblemTrackingLink.objects.create(ticket=ticket, tracking_token='test-queue-link')
        self.escalated(ticket)
        self.assertEqual(self.client.get('/api/dashboard/').data['counts']['resend_tracking_links'], 1)
        self.assertEqual(self.client.get('/api/dashboard/').data['counts']['customer_service_other'], 0)
