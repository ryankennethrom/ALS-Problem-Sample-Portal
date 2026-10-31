"""Dependency-free behavioral checks of terminal tracking-link lifecycle logic."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
source = ast.parse((ROOT / 'models.py').read_text())
sample_model = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'ProblemSample')
methods = [node for node in sample_model.body if isinstance(node, ast.FunctionDef) and node.name in {
    'expected_tracking_link_expiration', 'apply_acknowledgement_status_transition',
}]
namespace = {
    'timedelta': timedelta,
    'TRACKING_LINK_DAYS': 30,
    'TRACKING_LINK_EXPIRING_STATUSES': {'Disposed', 'Back to testing', 'Shipped back to client', 'To be Disposed'},
    'TERMINAL_PROBLEM_STATUSES': ['Disposed', 'Back to testing', 'Shipped back to client'],
    'DISPOSE_AUTOMATICALLY_NO': 'No',
}
behavior = ast.Module(body=[ast.ClassDef(name='TicketLifecycle', bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])
exec(compile(ast.fix_missing_locations(behavior), str(ROOT / 'models.py'), 'exec'), namespace)

class FakeTicket(namespace['TicketLifecycle']):
    def __init__(self, workflow, duration, anchor=None):
        self.workflow_status = workflow
        self.table_id = 'table'
        self.table = SimpleNamespace(terminal_tracking_link_days=duration)
        self.acknowledgement_status_changed_at = anchor
        self.current_workflow = workflow
        self.dispose_automatically = False
        self.back_to_testing_notified_at = None
        self.acknowledged_at = None
        self.customer_acknowledgement_action = ''
        self.saved_expiration = None

    def apply_intercolumn_value_controllers(self, *, strict=False):
        return set()

    def set_tracking_link_expiration(self, expires_at):
        self.saved_expiration = expires_at

class TerminalExpiryPureTests(unittest.TestCase):
    when = datetime(2026, 10, 29, 13, tzinfo=timezone.utc)

    def test_default_thirty_days_in_terminal(self):
        self.assertEqual(FakeTicket('Disposed', 30, self.when).expected_tracking_link_expiration(), self.when + timedelta(days=30))

    def test_custom_days_all_terminal_states(self):
        for state in ['Disposed', 'Back to testing', 'Shipped back to client']:
            with self.subTest(state=state):
                self.assertEqual(FakeTicket(state, 7, self.when).expected_tracking_link_expiration(), self.when + timedelta(days=7))

    def test_never_returns_none(self):
        self.assertIsNone(FakeTicket('Disposed', None, self.when).expected_tracking_link_expiration())

    def test_zero_is_immediate(self):
        self.assertEqual(FakeTicket('Disposed', 0, self.when).expected_tracking_link_expiration(), self.when)

    def test_pending_uses_thirty_not_admin_terminal_policy(self):
        for duration in (None, 0, 365):
            self.assertEqual(FakeTicket('To be Disposed', duration, self.when).expected_tracking_link_expiration(), self.when + timedelta(days=30))

    def test_no_anchor_is_unexpired(self):
        self.assertIsNone(FakeTicket('Disposed', 10).expected_tracking_link_expiration())

    def test_terminal_transition_updates_the_persisted_link_expiry(self):
        fake = FakeTicket('Disposed', None)
        update_fields = fake.apply_acknowledgement_status_transition('Follow Up Required', changed_at=self.when)
        self.assertIn('acknowledgement_status_changed_at', update_fields)
        self.assertEqual(fake.acknowledgement_status_changed_at, self.when)
        self.assertIsNone(fake.saved_expiration)

    def test_terminal_transition_with_days_applies_custom_setting(self):
        fake = FakeTicket('Back to testing', 12)
        fake.apply_acknowledgement_status_transition('To be back to testing', changed_at=self.when)
        self.assertEqual(fake.saved_expiration, self.when + timedelta(days=12))

    def test_reopen_into_followup_clears_link_expiration(self):
        fake = FakeTicket('Follow Up Required', None, self.when)
        fake.saved_expiration = self.when + timedelta(days=30)
        fake.apply_acknowledgement_status_transition('Disposed', changed_at=self.when)
        self.assertIsNone(fake.saved_expiration)
        self.assertIsNone(fake.acknowledgement_status_changed_at)

    def test_unique_token_and_expiry_database_indexes_remain(self):
        tracking = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'ProblemTrackingLink')
        fields = {n.targets[0].id: ast.unparse(n.value) for n in tracking.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}
        self.assertIn('unique=True', fields['tracking_token'])
        self.assertIn('db_index=True', fields['expires_at'])

if __name__ == '__main__':
    unittest.main()
