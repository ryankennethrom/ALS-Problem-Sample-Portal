"""Dependency-free behavioral tests for disabling disposal during Client Email escalation."""
from datetime import timedelta
import unittest

from problem_samples import test_client_email_priority_pure as fixture


class ClientEmailEscalationDisposalTests(unittest.TestCase):
    def setUp(self):
        self.ticket, self.events, self.escalate = fixture.PriorityTests().setup()

    def test_escalation_disables_yes_and_audits_the_change(self):
        self.ticket.custom_values['dispose-automatically'] = 'Yes'
        self.assertTrue(self.ticket.dispose_automatically)
        self.assertTrue(self.escalate(self.ticket, now=fixture.NOW))
        self.assertEqual(self.ticket.workflow_status, 'Follow Up Required')
        self.assertEqual(self.ticket.custom_values['dispose-automatically'], 'No')
        self.assertFalse(self.ticket.dispose_automatically)
        self.assertEqual(self.ticket.custom_values['client-contact-email'], ['d@example.com'])
        self.assertEqual(self.ticket.client_email_priority_state['client-email-column-id'], 1)
        self.assertEqual(self.events[0]['details']['changes'][-1], {
            'field': 'Dispose Automatically', 'before': 'Yes', 'after': 'No',
        })
        self.assertIn('custom_values', self.ticket.saves[0])

    def test_escalation_with_disposal_already_off_remains_off_without_false_change(self):
        self.ticket.custom_values['dispose-automatically'] = 'No'
        self.assertTrue(self.escalate(self.ticket, now=fixture.NOW))
        self.assertEqual(self.ticket.custom_values['dispose-automatically'], 'No')
        self.assertFalse(any(change['field'] == 'Dispose Automatically'
                             for change in self.events[0]['details']['changes']))

    def test_missing_original_disposal_value_is_normalized_to_no(self):
        self.ticket.custom_values.pop('dispose-automatically', None)
        self.assertTrue(self.escalate(self.ticket, now=fixture.NOW))
        self.assertEqual(self.ticket.custom_values['dispose-automatically'], 'No')
        self.assertFalse(any(change['field'] == 'Dispose Automatically'
                             for change in self.events[0]['details']['changes']))

    def test_not_due_does_not_disable_existing_disposal(self):
        self.ticket.custom_values['dispose-automatically'] = 'Yes'
        self.ticket.client_email_last_tracking_sent_at = fixture.NOW - timedelta(hours=2)
        self.assertFalse(self.escalate(self.ticket, now=fixture.NOW))
        self.assertEqual(self.ticket.custom_values['dispose-automatically'], 'Yes')
        self.assertEqual(self.events, [])

    def test_no_available_next_priority_does_not_disable_disposal(self):
        self.ticket, self.events, self.escalate = fixture.PriorityTests().setup(contacts={})
        self.ticket.custom_values['dispose-automatically'] = 'Yes'
        self.assertFalse(self.escalate(self.ticket, now=fixture.NOW))
        self.assertEqual(self.ticket.custom_values['dispose-automatically'], 'Yes')
        self.assertEqual(self.events, [])

    def test_escalation_still_idempotent_after_disabling_disposal(self):
        self.ticket.custom_values['dispose-automatically'] = 'Yes'
        self.assertTrue(self.escalate(self.ticket, now=fixture.NOW))
        self.assertFalse(self.escalate(self.ticket, now=fixture.NOW))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(len(self.ticket.saves), 1)
        self.assertEqual(self.ticket.custom_values['dispose-automatically'], 'No')


if __name__ == '__main__':
    unittest.main()
