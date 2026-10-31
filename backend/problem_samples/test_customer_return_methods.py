"""Tests for customer return methods on both /track and legacy /acknowledge links."""
from django.test import TestCase

from .models import (
    CURRENT_WORKFLOW_DEFAULT,
    DISPOSE_AUTOMATICALLY_NO,
    PROBLEM_STATUS_SHIPPED_BACK,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
    ProblemHistory,
    ProblemSample,
    ProblemTable,
    ProblemTrackingLink,
    generate_acknowledgement_token,
)


class CustomerReturnMethodTests(TestCase):
    def setUp(self):
        table = ProblemTable.objects.create(name='Return methods')
        self.problem = ProblemSample.objects.create(
            table=table,
            problem_number=321,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={
                SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: DISPOSE_AUTOMATICALLY_NO,
            },
        )
        ProblemTrackingLink.objects.create(
            ticket=self.problem, tracking_token=generate_acknowledgement_token(),
        )
        self.url = f'/api/public/problem-sample-tracking/{self.problem.acknowledgement_token}/'

    def respond(self, **fields):
        return self.client.post(
            self.url,
            data={'action': 'ship_back', 'signature': 'Customer Name', **fields},
            content_type='application/json',
        )

    def latest_selection(self):
        return ProblemHistory.objects.filter(problem=self.problem, details__customer_action='ship_back').first()

    def test_courier_account_queues_shipping_and_records_account(self):
        result = self.respond(shipping_method='courier_account', courier_name='Purolator', courier_account_number='AB-123456')
        self.assertEqual(result.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, PROBLEM_STATUS_TO_BE_SHIPPED_BACK)
        history = self.latest_selection()
        self.assertEqual(history.details['customer_shipping_method'], 'courier_account')
        self.assertEqual(history.details['customer_courier_name'], 'Purolator')
        self.assertEqual(history.details['customer_courier_account_number'], 'AB-123456')
        self.assertIn('courier account', history.summary.lower())
        self.assertEqual(result.data['customer_action_label'], 'I want these sample(s) back — Provide your courier name and account number')
        self.assertEqual(history.details['customer_action_label'], result.data['customer_action_label'])

    def test_courier_fields_trim_and_normalize_whitespace(self):
        result = self.respond(
            shipping_method='courier_account',
            courier_name='  Federal   Express ',
            courier_account_number=' AB  123 ',
        )
        self.assertEqual(result.status_code, 200)
        history = self.latest_selection()
        self.assertEqual(history.details['customer_courier_name'], 'Federal Express')
        self.assertEqual(history.details['customer_courier_account_number'], 'AB 123')

    def test_pickup_queues_shipping_and_records_method(self):
        result = self.respond(shipping_method='pickup')
        self.assertEqual(result.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, PROBLEM_STATUS_TO_BE_SHIPPED_BACK)
        history = self.latest_selection()
        self.assertEqual(history.details['customer_shipping_method'], 'pickup')
        self.assertNotIn('customer_courier_name', history.details)
        self.assertNotIn('customer_courier_account_number', history.details)
        self.assertEqual(result.data['customer_action_label'], 'I want these sample(s) back — Pick up in person')

    def test_quote_returns_to_customer_service_follow_up(self):
        first = self.respond(shipping_method='pickup')
        self.assertEqual(first.status_code, 200)
        result = self.respond(shipping_method='shipping_quote')
        self.assertEqual(result.status_code, 200)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertEqual(self.problem.customer_acknowledgement_action, 'ship_back')
        history = self.latest_selection()
        self.assertEqual(history.details['customer_shipping_method'], 'shipping_quote')
        self.assertIn('shipping charges', history.summary.lower())
        self.assertEqual(result.data['customer_action_label'], 'I want these sample(s) back — Receive a quote for the shipping charges')
        self.assertTrue(result.data['can_choose_action'])
        self.assertEqual(self.client.get(self.url).data['customer_action_label'], result.data['customer_action_label'])

    def test_missing_method_does_not_acknowledge_or_modify_ticket(self):
        response = self.respond()
        self.assertEqual(response.status_code, 400)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_DEFAULT)
        self.assertIsNone(self.problem.acknowledged_at)
        self.assertFalse(self.problem.history.exists())

    def test_invalid_account_and_unexpected_account_are_rejected(self):
        for fields in (
            {'shipping_method': 'courier_account'},
            {'shipping_method': 'courier_account', 'courier_account_number': 'ABC123'},
            {'shipping_method': 'courier_account', 'courier_name': 'FedEx'},
            {'shipping_method': 'courier_account', 'courier_name': 'X' * 201, 'courier_account_number': 'ABC123'},
            {'shipping_method': 'pickup', 'courier_name': 'UPS'},
            {'shipping_method': 'shipping_quote', 'courier_name': 'UPS'},
            {'shipping_method': 'dispose', 'courier_name': 'UPS'},
            {'shipping_method': 'pickup', 'courier_account_number': 'ABC123'},
            {'shipping_method': 'shipping_quote', 'courier_account_number': 'ABC123'},
            {'shipping_method': 'wrong'},
            {'shipping_method': 'courier_account', 'courier_name': 'UPS', 'courier_account_number': 'X' * 201},
        ):
            with self.subTest(fields=fields):
                self.assertEqual(self.respond(**fields).status_code, 400)
        self.assertFalse(self.problem.history.exists())

    def test_customer_cannot_change_response_after_shipping_completed(self):
        self.problem.current_workflow = PROBLEM_STATUS_SHIPPED_BACK
        self.problem.custom_values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_SHIPPED_BACK
        self.problem.save(update_fields=['current_workflow', 'custom_values'])
        response = self.respond(shipping_method='pickup')
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.problem.history.exists())

    def test_legacy_return_selection_shows_new_generic_label(self):
        self.problem.customer_acknowledgement_action = 'ship_back'
        self.problem.save(update_fields=['customer_acknowledgement_action'])
        ProblemHistory.objects.create(
            problem=self.problem, action=ProblemHistory.ACTION_UPDATED,
            summary='Customer selected: Ship back',
            details={'customer_action': 'ship_back', 'customer_action_label': 'Ship back'},
        )
        response = self.client.get(self.url)
        # Existing records are still readable without needing a method set retroactively.
        # This is a legacy response label change, not a data rewrite.
        self.assertEqual(response.data['customer_action_label'], 'I want these sample(s) back')
