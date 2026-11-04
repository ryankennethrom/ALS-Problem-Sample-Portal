"""Dependency-free tests of migration 0102's historical timestamp selection."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

PATH = Path(__file__).with_name('migrations') / '0102_backfill_client_email_priority_history.py'
TREE = ast.parse(PATH.read_text(encoding='utf-8'))
HELPERS = ('_latest_history_dates', '_backfilled_dates')
module = ast.Module(
    body=[node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in HELPERS],
    type_ignores=[],
)
namespace = {}
exec(compile(ast.fix_missing_locations(module), str(PATH), 'exec'), namespace)
latest_dates = namespace['_latest_history_dates']
backfill = namespace['_backfilled_dates']
T0 = datetime(2026, 10, 22, 12, 57, 44, tzinfo=timezone.utc)


class HistoryBackfillPureTests(unittest.TestCase):
    def test_selects_latest_confirmed_send_per_ticket(self):
        self.assertEqual(latest_dates([
            ('ticket-a', T0 + timedelta(days=1)), ('ticket-a', T0),
            ('ticket-b', T0 + timedelta(hours=2)),
        ]), {'ticket-a': T0 + timedelta(days=1), 'ticket-b': T0 + timedelta(hours=2)})

    def test_missing_send_history_does_not_invent_a_timer(self):
        self.assertEqual(backfill(None, None, None, None, None), (None, None))

    def test_october_send_initializes_existing_ticket(self):
        self.assertEqual(backfill(None, None, None, T0, None), (T0, None))

    def test_acknowledgement_counts_as_customer_activity(self):
        ack = T0 + timedelta(hours=20)
        self.assertEqual(backfill(None, None, ack, T0, None), (T0, ack))

    def test_latest_customer_response_wins_over_initial_acknowledgement(self):
        ack = T0 + timedelta(hours=1)
        response = T0 + timedelta(hours=26)
        self.assertEqual(backfill(None, None, ack, T0, response), (T0, response))

    def test_preserves_current_non_null_timestamps(self):
        current_send = T0 + timedelta(days=9)
        current_response = T0 + timedelta(days=10)
        self.assertEqual(backfill(current_send, current_response, None, T0, T0),
                         (current_send, current_response))

    def test_migration_filters_only_confirmed_link_sends_and_public_customer_history(self):
        source = PATH.read_text(encoding='utf-8')
        self.assertIn('action=\'customer_notification\'', source)
        self.assertIn('summary=TRACKING_SENT_SUMMARY', source)
        self.assertIn("Q(action='acknowledged')", source)
        self.assertIn('Q(details__responded_via__in=CUSTOMER_RESPONSE_SOURCES)', source)
        self.assertIn("('problem_samples', '0101_client_email_priority_escalation')", source)
        self.assertIn('migrations.RunPython.noop', source)
        self.assertNotIn('ProblemHistory.objects.create', source)

    def test_backfill_does_not_modify_original_disposal_start_or_workflow(self):
        code = ast.unparse(next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                                and n.name == 'backfill_from_history'))
        self.assertNotIn('automatic_disposal_started_at', code)
        self.assertNotIn('current_workflow', code)
        self.assertIn('bulk_update', code)


if __name__ == '__main__':
    unittest.main()
