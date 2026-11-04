"""Dependency-free tests that execute the actual priority escalation decision code."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).with_name('client_email_escalation.py')
TREE = ast.parse(SOURCE.read_text())
FUNCS = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in ('try_escalate_ticket', '_infer_legacy_priority')]
CODE = compile(ast.fix_missing_locations(ast.Module(body=FUNCS, type_ignores=[])), str(SOURCE), 'exec')
NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


class FakeColumn:
    def __init__(self):
        self.id = 'client-email-column-id'
        self.name = 'Client Contact Email'
        self.field_key = 'client-contact-email'
        self.client_email_fallback_hours = 24
        self.dependencies = [SimpleNamespace(field_key='end-user', name='End User'),
                             SimpleNamespace(field_key='distributor', name='Distributor'),
                             SimpleNamespace(field_key='other-company', name='Other')]

    def ordered_client_email_dependency_columns(self):
        return self.dependencies


class FakeTicket:
    def __init__(self, column):
        self.table = SimpleNamespace(columns=SimpleNamespace(filter=lambda **kw: [column]))
        self.current_workflow = 'Waiting for Customer Response'
        self.workflow_status = 'Waiting for Customer Response'
        self.client_email_last_tracking_sent_at = NOW - timedelta(hours=25)
        self.client_email_last_customer_response_at = None
        self.client_email_priority_state = {column.id: 0}
        self.custom_values = {'end-user': 'Acme', 'distributor': 'Distributor Co',
                              'other-company': 'Second Co', 'client-contact-email': ['a@example.com']}
        self.saves = []

    @property
    def dispose_automatically(self):
        return self.custom_values.get('dispose-automatically') == 'Yes'

    def set_workflow_status(self, value):
        self.workflow_status = value
        self.current_workflow = value
        self.custom_values['current-workflow'] = value

    def save(self, update_fields):
        self.saves.append(update_fields)


class PriorityTests(unittest.TestCase):
    def setup(self, contacts=None):
        col = FakeColumn()
        ticket = FakeTicket(col)
        events = []
        contacts = contacts if contacts is not None else {'Distributor Co': ['d@example.com'], 'Second Co': ['s@example.com']}
        env = {
            'CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER': 'Waiting for Customer Response',
            'CURRENT_WORKFLOW_DEFAULT': 'Follow Up Required',
            'SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY': 'dispose-automatically',
            'DISPOSE_AUTOMATICALLY_YES': 'Yes',
            'DISPOSE_AUTOMATICALLY_NO': 'No',
            'timedelta': timedelta,
            'ProblemColumn': SimpleNamespace(TYPE_CLIENT_EMAIL='client_email'),
            '_emails_for_company': lambda company: contacts.get(company, []),
            'ProblemHistory': SimpleNamespace(ACTION_UPDATED='updated', objects=SimpleNamespace(create=lambda **kwargs: events.append(kwargs))),
        }
        exec(CODE, env)
        return ticket, events, env['try_escalate_ticket']

    def test_after_timeout_switches_to_next_priority_and_records_reason(self):
        ticket, events, escalate = self.setup()
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(ticket.workflow_status, 'Follow Up Required')
        self.assertEqual(ticket.client_email_priority_state['client-email-column-id'], 1)
        self.assertEqual(ticket.custom_values['client-contact-email'], ['d@example.com'])
        self.assertEqual(events[0]['details']['reason'],
                         'End User has not responded for a while. The client contact email field has been changed to Distributor. Please resend the tracking link.')
        self.assertNotIn('Dependency Field Priority', events[0]['details']['reason'])
        self.assertIn('Please resend the tracking link.', events[0]['details']['reason'])
        self.assertEqual(len(ticket.saves), 1)
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(len(events), 1)

    def test_legacy_saved_emails_identify_distributor_as_original_priority(self):
        ticket, events, escalate = self.setup({'Acme': ['a@example.com'],
                                              'Distributor Co': ['d@example.com'],
                                              'Second Co': ['s@example.com']})
        ticket.client_email_priority_state = {}
        ticket.custom_values['client-contact-email'] = ['d@example.com']
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(ticket.client_email_priority_state['client-email-column-id'], 2)
        self.assertEqual(ticket.custom_values['client-contact-email'], ['s@example.com'])
        self.assertTrue(events[0]['details']['inferred_original_priority'])
        self.assertIn('Distributor has not responded', events[0]['details']['reason'])
        self.assertIn('changed to Other.', events[0]['details']['reason'])

    def test_ambiguous_legacy_saved_emails_do_not_guess_higher_priority(self):
        ticket, events, escalate = self.setup({'Acme': ['a@example.com'],
                                              'Distributor Co': ['a@example.com'],
                                              'Second Co': ['s@example.com']})
        ticket.client_email_priority_state = {}
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(ticket.client_email_priority_state['client-email-column-id'], 1)
        self.assertFalse(events[0]['details']['inferred_original_priority'])

    def test_legacy_many_matches_choose_next_priority_after_best_matching_list(self):
        ticket, events, escalate = self.setup({'Acme': ['a@example.com'],
                                              'Distributor Co': ['a@example.com', 'b@example.com'],
                                              'Second Co': ['s@example.com']})
        ticket.client_email_priority_state = {}
        ticket.custom_values['client-contact-email'] = ['a@example.com', 'b@example.com', 'unmatched@example.com']
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(ticket.client_email_priority_state['client-email-column-id'], 2)
        self.assertEqual(events[0]['details']['from_priority'], 2)
        self.assertIn('Distributor has not responded', events[0]['details']['reason'])

    def test_legacy_priority_one_empty_list_is_never_used_for_inference(self):
        ticket, events, escalate = self.setup({'Acme': [],
                                              'Distributor Co': ['d@example.com'],
                                              'Second Co': ['s@example.com']})
        ticket.client_email_priority_state = {}
        ticket.custom_values['client-contact-email'] = ['d@example.com']
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(events[0]['details']['from_priority'], 2)
        self.assertEqual(events[0]['details']['to_priority'], 3)

    def test_legacy_without_saved_emails_does_not_guess_a_source(self):
        ticket, events, escalate = self.setup({'Acme': [],
                                              'Distributor Co': ['d@example.com'],
                                              'Second Co': ['s@example.com']})
        ticket.client_email_priority_state = {}
        ticket.custom_values['client-contact-email'] = []
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(events, [])

    def test_explicit_priority_wins_over_saved_email_heuristic(self):
        ticket, events, escalate = self.setup({'Acme': ['a@example.com'],
                                              'Distributor Co': ['d@example.com'],
                                              'Second Co': ['s@example.com']})
        ticket.client_email_priority_state = {'client-email-column-id': 1}
        ticket.custom_values['client-contact-email'] = ['a@example.com']
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(ticket.client_email_priority_state['client-email-column-id'], 2)
        self.assertFalse(events[0]['details']['inferred_original_priority'])

    def test_zero_hours_escalates_at_confirmed_send_time(self):
        ticket, events, escalate = self.setup()
        zero_column = FakeColumn()
        zero_column.client_email_fallback_hours = 0
        ticket.client_email_last_tracking_sent_at = NOW
        ticket.client_email_last_customer_response_at = None
        ticket.table.columns.filter = lambda **kw: [zero_column]
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(ticket.workflow_status, 'Follow Up Required')
        self.assertEqual(len(events), 1)

    def test_zero_hours_uses_latest_customer_response_without_waiting(self):
        ticket, events, escalate = self.setup()
        zero_column = FakeColumn()
        zero_column.client_email_fallback_hours = 0
        ticket.client_email_last_tracking_sent_at = NOW - timedelta(days=5)
        ticket.client_email_last_customer_response_at = NOW
        ticket.table.columns.filter = lambda **kw: [zero_column]
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(len(events), 1)

    def test_zero_hours_never_escalates_without_confirmed_send(self):
        ticket, events, escalate = self.setup()
        zero_column = FakeColumn()
        zero_column.client_email_fallback_hours = 0
        ticket.client_email_last_tracking_sent_at = None
        ticket.table.columns.filter = lambda **kw: [zero_column]
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(events, [])

    def test_not_due_does_not_change_anything(self):
        ticket, events, escalate = self.setup()
        ticket.client_email_last_tracking_sent_at = NOW - timedelta(hours=23)
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(events, [])

    def test_recent_customer_response_resets_timer(self):
        ticket, events, escalate = self.setup()
        ticket.client_email_last_customer_response_at = NOW - timedelta(hours=2)
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(events, [])

    def test_only_waiting_workflow_is_eligible(self):
        ticket, events, escalate = self.setup()
        ticket.workflow_status = 'To be shipped back to client'
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(events, [])

    def test_no_tracking_send_does_not_escalate(self):
        ticket, events, escalate = self.setup()
        ticket.client_email_last_tracking_sent_at = None
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(events, [])

    def test_skips_missing_intermediate_email_list(self):
        ticket, events, escalate = self.setup({'Second Co': ['s@example.com']})
        self.assertTrue(escalate(ticket, now=NOW))
        self.assertEqual(ticket.client_email_priority_state['client-email-column-id'], 2)
        self.assertEqual(ticket.custom_values['client-contact-email'], ['s@example.com'])

    def test_last_priority_has_no_next_contact(self):
        ticket, events, escalate = self.setup()
        ticket.client_email_priority_state['client-email-column-id'] = 2
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(events, [])

    def test_no_available_fallback_preserves_ticket(self):
        ticket, events, escalate = self.setup({})
        self.assertFalse(escalate(ticket, now=NOW))
        self.assertEqual(ticket.workflow_status, 'Waiting for Customer Response')
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
