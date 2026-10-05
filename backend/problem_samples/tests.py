from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .automatic_disposal import transition_due_automatic_disposals
from .models import (
    DISPOSE_AUTOMATICALLY_NO,
    DISPOSE_AUTOMATICALLY_YES,
    PROBLEM_STATUS_DEFAULT,
    PROBLEM_STATUS_CHOICES,
    CURRENT_WORKFLOW_DEFAULT,
    CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
    CURRENT_WORKFLOW_CHOICES,
    PROBLEM_STATUS_TO_BE_DISPOSED,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_BACK_TO_TESTING,
    PROBLEM_STATUS_SHIPPED_BACK,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
    AutomaticDisposalExpiryEvent,
    ProblemHistory,
    ProblemSample,
    ProblemTrackingLink,
    generate_acknowledgement_token,
    ProblemTable,
)


class AutomaticDisposalTransitionTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(
            name='Automatic disposal test',
            is_default=True,
            pt_days=1,
        )

    def _problem(self, *, workflow=CURRENT_WORKFLOW_DEFAULT, auto=DISPOSE_AUTOMATICALLY_YES, started_at=None):
        return ProblemSample.objects.create(
            table=self.table,
            problem_number=1,
            status=PROBLEM_STATUS_DEFAULT,
            current_workflow=workflow,
            automatic_disposal_started_at=started_at or (timezone.now() - timedelta(days=2)),
            custom_values={
                'status': PROBLEM_STATUS_DEFAULT,
                SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: workflow,
                SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: auto,
            },
        )

    def test_due_automatic_disposal_becomes_to_be_disposed(self):
        problem = self._problem()

        transitioned = transition_due_automatic_disposals(now=timezone.now())

        self.assertEqual(transitioned, 1)
        problem.refresh_from_db()
        self.assertEqual(problem.workflow_status, PROBLEM_STATUS_TO_BE_DISPOSED)
        self.assertEqual(problem.status, PROBLEM_STATUS_DEFAULT)
        self.assertEqual(problem.custom_values['status'], PROBLEM_STATUS_DEFAULT)
        self.assertEqual(
            problem.custom_values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY],
            DISPOSE_AUTOMATICALLY_NO,
        )
        self.assertTrue(problem.is_disposal_eligible)
        self.assertTrue(
            ProblemHistory.objects.filter(
                problem=problem,
                summary='Automatic disposal period ended',
            ).exists()
        )
        event = AutomaticDisposalExpiryEvent.objects.get(ticket=problem)
        self.assertEqual(event.effective_at, problem.automatic_disposal_started_at + timedelta(days=1))

        # Re-running the expiry sweep must not double-count the transition.
        self.assertEqual(transition_due_automatic_disposals(now=timezone.now()), 0)
        self.assertEqual(AutomaticDisposalExpiryEvent.objects.filter(ticket=problem).count(), 1)

        # Historical analytics survive ticket deletion without retaining ticket data.
        problem.delete()
        event.refresh_from_db()
        self.assertIsNone(event.ticket_id)

    def test_not_yet_due_does_not_transition(self):
        problem = self._problem(started_at=timezone.now())

        transitioned = transition_due_automatic_disposals(now=timezone.now())

        self.assertEqual(transitioned, 0)
        problem.refresh_from_db()
        self.assertEqual(problem.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(
            problem.custom_values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY],
            DISPOSE_AUTOMATICALLY_YES,
        )

    def test_protected_workflow_status_is_never_overridden(self):
        problem = self._problem(workflow=PROBLEM_STATUS_TO_BE_SHIPPED_BACK)

        transitioned = transition_due_automatic_disposals(now=timezone.now())

        self.assertEqual(transitioned, 0)
        problem.refresh_from_db()
        self.assertEqual(problem.workflow_status, PROBLEM_STATUS_TO_BE_SHIPPED_BACK)


class CustomerRecentRowModifierTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from types import SimpleNamespace
        from .models import ProblemColumn, TERMINAL_PROBLEM_STATUSES
        from .serializers import ProblemSampleSerializer

        self.SimpleNamespace = SimpleNamespace
        self.ProblemSampleSerializer = ProblemSampleSerializer
        self.staff = User.objects.create_user(
            username='staff.user',
            email='staff.user@alsglobal.com',
            password='temporary-test-password',
        )
        self.table = ProblemTable.objects.create(name='Customer modifier test', is_default=True)
        ProblemColumn.objects.create(
            table=self.table,
            name='Status',
            field_key='status',
            column_type=ProblemColumn.TYPE_CHOICE,
            required=True,
            choices=list(PROBLEM_STATUS_CHOICES),
            default_value=PROBLEM_STATUS_DEFAULT,
            is_system=True,
            position=0,
        )
        ProblemColumn.objects.create(
            table=self.table,
            name='Current Workflow',
            field_key=SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE,
            required=True,
            choices=list(CURRENT_WORKFLOW_CHOICES),
            default_value=CURRENT_WORKFLOW_DEFAULT,
            is_system=True,
            position=1,
        )
        ProblemColumn.objects.create(
            table=self.table,
            name='Dispose Automatically',
            field_key=SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE,
            required=True,
            choices=[DISPOSE_AUTOMATICALLY_YES, DISPOSE_AUTOMATICALLY_NO],
            default_value=DISPOSE_AUTOMATICALLY_NO,
            is_system=True,
            position=2,
        )
        self.modifier_column = ProblemColumn.objects.create(
            table=self.table,
            name='Recent Row Modifier',
            field_key='recent-row-modifier',
            column_type=ProblemColumn.TYPE_RECENT_ROW_MODIFIER,
            position=3,
        )
        self.problem = ProblemSample.objects.create(
            table=self.table,
            problem_number=1,
            status=PROBLEM_STATUS_DEFAULT,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            modified_by=self.staff,
            custom_values={
                'status': PROBLEM_STATUS_DEFAULT,
                SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: DISPOSE_AUTOMATICALLY_NO,
                self.modifier_column.field_key: self.staff.email,
            },
        )
        ProblemTrackingLink.objects.create(ticket=self.problem, tracking_token=generate_acknowledgement_token())

    def test_public_tracker_uses_customer_facing_ticket_status_labels(self):
        tracking_url = f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/'
        expected = {
            CURRENT_WORKFLOW_DEFAULT: 'Waiting for ALS Edmonton',
            CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER: 'Waiting for your response',
            PROBLEM_STATUS_TO_BE_DISPOSED: 'To be disposed',
            PROBLEM_STATUS_TO_BE_SHIPPED_BACK: 'To be shipped back',
            PROBLEM_STATUS_DISPOSED: 'Disposed',
            PROBLEM_STATUS_SHIPPED_BACK: 'Shipped back',
            PROBLEM_STATUS_TO_BE_BACK_TO_TESTING: 'To be back to testing',
            PROBLEM_STATUS_BACK_TO_TESTING: 'Back to testing',
        }

        for workflow, label in expected.items():
            with self.subTest(workflow=workflow):
                values = dict(self.problem.custom_values)
                values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = workflow
                ProblemSample.objects.filter(pk=self.problem.pk).update(
                    current_workflow=workflow,
                    custom_values=values,
                    tracking_link_expires_at=None,
                )
                response = self.client.get(tracking_url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['ticket_status'], label)

    def test_customer_tracking_action_becomes_recent_row_modifier(self):
        before_modified_at = self.problem.modified_at
        response = self.client.post(
            f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/',
            data={'action': 'dispose', 'signature': 'Customer Name'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, PROBLEM_STATUS_TO_BE_DISPOSED)
        self.assertEqual(self.problem.status, PROBLEM_STATUS_DEFAULT)
        self.assertEqual(self.problem.custom_values['status'], PROBLEM_STATUS_DEFAULT)
        self.assertEqual(self.problem.custom_values[self.modifier_column.field_key], 'Customer')
        self.assertIsNone(self.problem.modified_by)
        self.assertGreater(self.problem.modified_at, before_modified_at)

    def test_customer_can_change_response_until_workflow_is_completed(self):
        tracking_url = f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/'

        first = self.client.post(
            tracking_url,
            data={'action': 'dispose', 'signature': 'Customer Name'},
            content_type='application/json',
        )
        self.assertEqual(first.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, PROBLEM_STATUS_TO_BE_DISPOSED)

        queued = self.client.get(tracking_url)
        self.assertEqual(queued.status_code, 200)
        self.assertEqual(queued.data['state'], 'acknowledged')
        self.assertTrue(queued.data['can_choose_action'])
        self.assertEqual(queued.data['customer_action'], 'dispose')

        changed_to_shipping = self.client.post(
            tracking_url,
            data={'action': 'ship_back', 'signature': 'Customer Name'},
            content_type='application/json',
        )
        self.assertEqual(changed_to_shipping.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, PROBLEM_STATUS_TO_BE_SHIPPED_BACK)
        self.assertEqual(self.problem.customer_acknowledgement_action, 'ship_back')

        changed_to_follow_up = self.client.post(
            tracking_url,
            data={
                'action': 'requested_info',
                'signature': 'Customer Name',
                'requested_information': 'Please review the updated information.',
            },
            content_type='application/json',
        )
        self.assertEqual(changed_to_follow_up.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(self.problem.customer_acknowledgement_action, 'requested_info')

    def test_customer_can_change_response_from_any_intermediate_queue(self):
        tracking_url = f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/'
        for workflow in (
            PROBLEM_STATUS_TO_BE_DISPOSED,
            PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
            PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
        ):
            with self.subTest(workflow=workflow):
                values = dict(self.problem.custom_values)
                values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = workflow
                ProblemSample.objects.filter(pk=self.problem.pk).update(
                    current_workflow=workflow,
                    custom_values=values,
                )
                response = self.client.post(
                    tracking_url,
                    data={'action': 'dispose', 'signature': 'Customer Name'},
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 200)
                self.problem.refresh_from_db()
                self.assertEqual(self.problem.workflow_status, PROBLEM_STATUS_TO_BE_DISPOSED)

    def test_customer_response_is_locked_after_completed_workflows(self):
        tracking_url = f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/'
        for workflow in (
            PROBLEM_STATUS_DISPOSED,
            PROBLEM_STATUS_BACK_TO_TESTING,
            PROBLEM_STATUS_SHIPPED_BACK,
        ):
            with self.subTest(workflow=workflow):
                values = dict(self.problem.custom_values)
                values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = workflow
                ProblemSample.objects.filter(pk=self.problem.pk).update(
                    current_workflow=workflow,
                    custom_values=values,
                    customer_acknowledgement_action='',
                )
                response = self.client.post(
                    tracking_url,
                    data={'action': 'dispose', 'signature': 'Customer Name'},
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 409)
                self.problem.refresh_from_db()
                self.assertEqual(self.problem.workflow_status, workflow)
                self.assertEqual(self.problem.customer_acknowledgement_action, '')

    def test_stop_eventual_disposal_is_no_longer_a_valid_customer_action(self):
        values = dict(self.problem.custom_values)
        values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_YES
        ProblemSample.objects.filter(pk=self.problem.pk).update(
            custom_values=values,
            automatic_disposal_started_at=timezone.now(),
        )
        response = self.client.post(
            f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/',
            data={'action': 'hold', 'signature': 'Customer Name'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_waiting_for_customer_is_active_and_customer_can_respond(self):
        from rest_framework.test import APIClient

        self.problem.set_workflow_status(CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)
        self.problem.save(update_fields=['custom_values', 'current_workflow'])
        second = ProblemSample.objects.create(
            table=self.table, problem_number=2, status=PROBLEM_STATUS_DEFAULT,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={'status': PROBLEM_STATUS_DEFAULT,
                           SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                           SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: DISPOSE_AUTOMATICALLY_NO},
        )
        staff = APIClient()
        staff.force_authenticate(self.staff)
        queue = staff.get('/api/problem-samples/follow-up-required/', {'table': str(self.table.pk)})
        self.assertEqual(queue.status_code, 200)
        self.assertEqual({item['id'] for item in queue.data}, {str(self.problem.pk), str(second.pk)})

        tracking_url = f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/'
        pending = self.client.get(tracking_url)
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.data['state'], 'pending')
        response = self.client.post(
            tracking_url,
            data={'action': 'requested_info', 'signature': 'Customer Name',
                  'requested_information': 'Please retest this sample.'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(self.problem.custom_values[self.modifier_column.field_key], 'Customer')
        self.assertEqual(self.problem.custom_values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY], DISPOSE_AUTOMATICALLY_NO)
        follow_up = staff.get('/api/problem-samples/follow-up-required/', {'table': str(self.table.pk)})
        self.assertEqual({item['id'] for item in follow_up.data}, {str(self.problem.pk), str(second.pk)})

    def test_waiting_for_customer_can_be_saved_by_staff(self):
        serializer = self.ProblemSampleSerializer(
            self.problem,
            data={'custom_values': {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER}},
            partial=True,
            context={'request': self.SimpleNamespace(user=self.staff)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(modified_by=self.staff)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)

    def test_later_staff_save_replaces_customer_modifier(self):
        self.client.post(
            f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/',
            data={'action': 'dispose', 'signature': 'Customer Name'},
            content_type='application/json',
        )
        self.problem.refresh_from_db()

        request = self.SimpleNamespace(user=self.staff)
        serializer = self.ProblemSampleSerializer(
            self.problem,
            data={'issue_description': 'Updated by staff'},
            partial=True,
            context={'request': request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(modified_by=self.staff)

        self.problem.refresh_from_db()
        self.assertEqual(
            self.problem.custom_values[self.modifier_column.field_key],
            self.staff.email,
        )
        self.assertEqual(self.problem.modified_by, self.staff)

    def test_descriptive_status_change_does_not_change_current_workflow(self):
        request = self.SimpleNamespace(user=self.staff)
        serializer = self.ProblemSampleSerializer(
            self.problem,
            data={'custom_values': {'status': 'IN PROGRESS'}},
            partial=True,
            context={'request': request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(modified_by=self.staff)

        self.problem.refresh_from_db()
        self.assertEqual(self.problem.status, 'IN PROGRESS')
        self.assertEqual(self.problem.custom_values['status'], 'IN PROGRESS')
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(
            self.problem.custom_values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY],
            CURRENT_WORKFLOW_DEFAULT,
        )


    def test_status_outside_fixed_set_is_rejected(self):
        request = self.SimpleNamespace(user=self.staff)
        serializer = self.ProblemSampleSerializer(
            self.problem,
            data={'custom_values': {'status': 'Waiting on lab'}},
            partial=True,
            context={'request': request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('status', serializer.errors['custom_values'])



class EmailTemplateAdminTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient
        from accounts.models import UserProfile

        self.client = APIClient()
        self.admin_user = User.objects.create_user(username='template.admin', password='test-password')
        UserProfile.objects.create(user=self.admin_user, is_admin=True)
        self.staff_user = User.objects.create_user(username='template.staff', password='test-password')
        UserProfile.objects.create(user=self.staff_user, is_admin=False)
        self.url = '/api/email-templates/customer-notification/'

    def test_staff_can_read_active_template(self):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('{{tracking_link}}', response.data['body_template'])

    def test_non_admin_cannot_edit_template(self):
        self.client.force_authenticate(self.staff_user)
        response = self.client.put(self.url, {
            'subject_template': 'Changed',
            'body_template': 'Link: {{tracking_link}}',
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_admin_can_edit_template(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.put(self.url, {
            'subject_template': 'Problem {{problem_id}}',
            'body_template': 'Please use {{tracking_link}}',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['subject_template'], 'Problem {{problem_id}}')

    def test_tracking_link_placeholder_is_required(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.put(self.url, {
            'subject_template': 'Problem {{problem_id}}',
            'body_template': 'No link here',
        }, format='json')
        self.assertEqual(response.status_code, 400)


class IntercolumnValueControllerTests(TestCase):
    def setUp(self):
        from .models import ProblemColumn
        self.ProblemColumn = ProblemColumn
        self.table = ProblemTable.objects.create(name='Intercolumn rules test')
        self.status = ProblemColumn.objects.create(
            table=self.table,
            name='Status',
            field_key='status',
            column_type=ProblemColumn.TYPE_CHOICE,
            choices=list(PROBLEM_STATUS_CHOICES),
            required=True,
            default_value=PROBLEM_STATUS_DEFAULT,
            is_system=True,
            position=0,
        )
        self.workflow = ProblemColumn.objects.create(
            table=self.table,
            name='Current Workflow',
            field_key=SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE,
            choices=list(CURRENT_WORKFLOW_CHOICES),
            required=True,
            default_value=CURRENT_WORKFLOW_DEFAULT,
            is_system=True,
            position=1,
        )
        self.auto = ProblemColumn.objects.create(
            table=self.table,
            name='Dispose Automatically',
            field_key=SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE,
            choices=[DISPOSE_AUTOMATICALLY_YES, DISPOSE_AUTOMATICALLY_NO],
            required=True,
            default_value=DISPOSE_AUTOMATICALLY_NO,
            is_system=True,
            position=2,
        )
        self.priority = ProblemColumn.objects.create(
            table=self.table,
            name='Priority',
            field_key='priority',
            column_type=ProblemColumn.TYPE_CHOICE,
            choices=['Low', 'High'],
            default_value='Low',
            position=3,
        )
        self.controller = ProblemColumn.objects.create(
            table=self.table,
            name='Escalation',
            field_key='escalation',
            column_type=ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER,
            position=4,
            intercolumn_rules=[{
                'other_column_id': str(self.priority.id),
                'direction': 'both',
                'when_other_equals': 'High',
                'set_controller_to': 'Urgent',
                'when_controller_equals': 'Normal',
                'set_other_to': 'Low',
            }],
        )

    def base_values(self):
        return {
            'status': PROBLEM_STATUS_DEFAULT,
            SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
            SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: DISPOSE_AUTOMATICALLY_NO,
            'priority': 'Low',
            'escalation': '',
        }

    def test_other_field_can_set_controller_value(self):
        from .models import apply_intercolumn_rules_to_values
        values = self.base_values()
        values['priority'] = 'High'
        updated, changed = apply_intercolumn_rules_to_values(self.table, values)
        self.assertEqual(updated['escalation'], 'Urgent')
        self.assertIn('escalation', changed)

    def test_controller_can_set_other_field_and_chain_back(self):
        from .models import apply_intercolumn_rules_to_values
        self.controller.intercolumn_rules = [{
            'other_column_id': str(self.priority.id),
            'direction': 'both',
            'when_other_equals': 'High',
            'set_controller_to': 'Urgent',
            'when_controller_equals': 'Normal',
            'set_other_to': 'High',
        }]
        self.controller.save(update_fields=['intercolumn_rules'])
        values = self.base_values()
        values['escalation'] = 'Normal'
        updated, changed = apply_intercolumn_rules_to_values(self.table, values)
        self.assertEqual(updated['priority'], 'High')
        self.assertEqual(updated['escalation'], 'Urgent')
        self.assertIn('priority', changed)
        self.assertIn('escalation', changed)

    def test_controller_rule_can_change_current_workflow(self):
        from .models import apply_intercolumn_rules_to_values
        self.controller.intercolumn_rules = [{
            'other_column_id': str(self.workflow.id),
            'direction': 'controller_to_other',
            'when_other_equals': None,
            'set_controller_to': None,
            'when_controller_equals': 'Dispose',
            'set_other_to': PROBLEM_STATUS_TO_BE_DISPOSED,
        }]
        self.controller.save(update_fields=['intercolumn_rules'])
        values = self.base_values()
        values['escalation'] = 'Dispose'
        values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_YES
        updated, _ = apply_intercolumn_rules_to_values(self.table, values)
        self.assertEqual(updated[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY], PROBLEM_STATUS_TO_BE_DISPOSED)
        self.assertEqual(updated[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY], DISPOSE_AUTOMATICALLY_NO)

    def test_nonconverging_cycle_is_rejected(self):
        from django.core.exceptions import ValidationError
        from .models import apply_intercolumn_rules_to_values
        self.controller.intercolumn_rules = [
            {
                'other_column_id': str(self.priority.id),
                'direction': 'other_to_controller',
                'when_other_equals': 'Low',
                'set_controller_to': 'A',
                'when_controller_equals': None,
                'set_other_to': None,
            },
            {
                'other_column_id': str(self.priority.id),
                'direction': 'controller_to_other',
                'when_other_equals': None,
                'set_controller_to': None,
                'when_controller_equals': 'A',
                'set_other_to': 'High',
            },
            {
                'other_column_id': str(self.priority.id),
                'direction': 'other_to_controller',
                'when_other_equals': 'High',
                'set_controller_to': 'B',
                'when_controller_equals': None,
                'set_other_to': None,
            },
            {
                'other_column_id': str(self.priority.id),
                'direction': 'controller_to_other',
                'when_other_equals': None,
                'set_controller_to': None,
                'when_controller_equals': 'B',
                'set_other_to': 'Low',
            },
        ]
        self.controller.save(update_fields=['intercolumn_rules'])
        with self.assertRaises(ValidationError):
            apply_intercolumn_rules_to_values(self.table, self.base_values())

    def test_serializer_applies_rule_on_row_save(self):
        from types import SimpleNamespace
        from django.contrib.auth.models import User
        from .serializers import ProblemSampleSerializer
        user = User.objects.create_user(username='controller.staff', email='controller.staff@alsglobal.com')
        problem = ProblemSample.objects.create(
            table=self.table,
            problem_number=1,
            status=PROBLEM_STATUS_DEFAULT,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values=self.base_values(),
        )
        serializer = ProblemSampleSerializer(
            problem,
            data={'custom_values': {'priority': 'High'}},
            partial=True,
            context={'request': SimpleNamespace(user=user)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        saved = serializer.save(modified_by=user)
        self.assertEqual(saved.custom_values['escalation'], 'Urgent')
