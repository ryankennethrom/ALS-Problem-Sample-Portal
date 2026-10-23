"""Regression cases for lab scoping, independent container serials and role administration.
Run with: python manage.py test problem_samples.test_multi_lab
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import Lab, UserProfile
from .labs import create_container
from .models import ProblemTable, ProblemSample, ProblemComment, ProblemMention


class LabIsolationTests(TestCase):
    def setUp(self):
        self.edmonton = Lab.objects.get(code='EDM')
        self.calgary = Lab.objects.create(name='Calgary', code='CGY')
        self.table = ProblemTable.objects.create(name='Lab isolation test')
        self.admin = User.objects.create_user(username='lab-admin', password='testpassA')
        UserProfile.objects.create(user=self.admin, is_admin=True, role='lab_technician', lab=self.edmonton)
        self.staff = User.objects.create_user(username='calgary-lab', password='testpassB', email='someone@alsglobal.com')
        UserProfile.objects.create(user=self.staff, role='lab_technician', lab=self.calgary)
        self.ed_ticket = ProblemSample.objects.create(table=self.table, lab=self.edmonton, problem_number=1)
        self.cg_ticket = ProblemSample.objects.create(table=self.table, lab=self.calgary, problem_number=2)
        self.client = APIClient()

    def test_disposal_search_serializes_lab_fields(self):
        """A search result must serialize without DRF's declared-field assertion."""
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/problem-samples/disposal-search/?q=1', HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 1, response.data)
        self.assertEqual(response.data[0]['id'], str(self.ed_ticket.pk))
        self.assertEqual(response.data[0]['lab'], self.edmonton.pk)
        self.assertEqual(response.data[0]['lab_name'], self.edmonton.name)
        self.assertEqual(response.data[0]['lab_code'], 'EDM')

    def test_disposal_browse_serializes_lab_fields(self):
        """The same lightweight serializer is also used by workflow queues."""
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/problem-samples/disposal-browse/', HTTP_X_ACTIVE_LAB='CGY')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 1, response.data)
        self.assertEqual(response.data[0]['id'], str(self.cg_ticket.pk))
        self.assertEqual(response.data[0]['lab_code'], 'CGY')

    def test_admin_changes_lab_and_sees_only_that_lab_tickets(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/problem-samples/', HTTP_X_ACTIVE_LAB='CGY')
        self.assertEqual(response.status_code, 200)
        ids = str(response.data)
        self.assertIn(str(self.cg_ticket.pk), ids)
        self.assertNotIn(str(self.ed_ticket.pk), ids)

    def test_nonadmin_cannot_select_other_lab(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get('/api/problem-samples/', HTTP_X_ACTIVE_LAB='EDM')
        self.assertEqual(response.status_code, 403)

    def test_container_ids_are_independent_per_lab(self):
        ed = create_container(self.edmonton, created_by=self.admin)
        cg = create_container(self.calgary, created_by=self.admin)
        self.assertEqual(ed.container_id, 'EDM PC-00001')
        self.assertEqual(cg.container_id, 'CGY PC-00001')

    def test_missing_lab_blocks_staff_login(self):
        no_lab = User.objects.create_user(username='new-staff', password='password123')
        UserProfile.objects.create(user=no_lab, role='customer_service')
        result = self.client.post('/api/auth/login/', {'username':'new-staff', 'password':'password123'}, format='json')
        self.assertEqual(result.status_code, 403)

    def test_admin_all_can_read_across_labs(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/problem-samples/', HTTP_X_ACTIVE_LAB='ALL')
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(self.ed_ticket.pk), str(response.data))
        self.assertIn(str(self.cg_ticket.pk), str(response.data))

    def test_admin_cannot_write_while_all_is_selected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/problem-samples/prepare-new/', {
            'table':str(self.table.pk), 'custom_values': {}, 'container_code':''
        }, format='json', HTTP_X_ACTIVE_LAB='ALL')
        self.assertEqual(response.status_code, 400)

    def test_admin_all_mention_summary_and_inbox_are_readable(self):
        """Lab: All must not trigger the single-lab write restriction in sidebar polling."""
        comment = ProblemComment.objects.create(problem=self.ed_ticket, body='Please review', author=self.staff)
        ProblemMention.objects.create(comment=comment, problem=self.ed_ticket,
                                      mentioned_user=self.admin, mentioned_by=self.staff)
        self.client.force_authenticate(self.admin)
        summary = self.client.get('/api/problem-samples/mentions/?summary=1', HTTP_X_ACTIVE_LAB='ALL')
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data['unread_count'], 1)
        inbox = self.client.get('/api/problem-samples/mentions/', HTTP_X_ACTIVE_LAB='ALL')
        self.assertEqual(inbox.status_code, 200, inbox.data)
        self.assertEqual(inbox.data['unread_count'], 1)
        self.assertEqual(len(inbox.data['results']), 1)

    def test_mention_summary_respects_selected_lab(self):
        for ticket in (self.ed_ticket, self.cg_ticket):
            comment = ProblemComment.objects.create(problem=ticket, body='Check ticket', author=self.staff)
            ProblemMention.objects.create(comment=comment, problem=ticket,
                                          mentioned_user=self.admin, mentioned_by=self.staff)
        self.client.force_authenticate(self.admin)
        for lab_code in ('EDM', 'CGY'):
            summary = self.client.get('/api/problem-samples/mentions/?summary=1', HTTP_X_ACTIVE_LAB=lab_code)
            self.assertEqual(summary.status_code, 200, summary.data)
            self.assertEqual(summary.data['unread_count'], 1)
        all_labs = self.client.get('/api/problem-samples/mentions/?summary=1', HTTP_X_ACTIVE_LAB='ALL')
        self.assertEqual(all_labs.status_code, 200, all_labs.data)
        self.assertEqual(all_labs.data['unread_count'], 2)
