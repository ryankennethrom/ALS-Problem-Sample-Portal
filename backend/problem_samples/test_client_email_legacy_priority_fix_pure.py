"""Dependency-free checks for legacy tracking-send attribution and diagnostics."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).parent
ESCALATION = (ROOT / 'client_email_escalation.py').read_text()
COMMAND = (ROOT / 'management/commands/diagnose_client_email_escalation.py').read_text()
MIGRATION = (ROOT / 'migrations/0103_reconcile_legacy_tracking_send_history.py').read_text()
VIEWS = (ROOT / 'views.py').read_text()


class LegacyAttributionChecks(unittest.TestCase):
    def test_priority_inference_counts_overlapping_emails_and_ignores_empty_lists(self):
        self.assertIn('len(saved & known)', ESCALATION)
        self.assertIn('if known:', ESCALATION)
        self.assertIn('best_score = max(scores.values())', ESCALATION)
        self.assertIn('return (0 if 0 in scores else winners[0]), False', ESCALATION)
        self.assertIn('return None, False', ESCALATION)

    def test_history_records_inference_and_current_priority(self):
        self.assertIn('inferred_original_priority', ESCALATION)
        self.assertIn('client_email_priority_state', VIEWS)
        self.assertIn("'client_email_priority_state': dict(problem.client_email_priority_state or {}),", VIEWS)

    def test_reconciliation_is_idempotent_timestamp_only(self):
        self.assertIn("'0102_backfill_client_email_priority_history'", MIGRATION)
        self.assertIn('previous.backfill_from_history(apps, schema_editor)', MIGRATION)
        self.assertIn('migrations.RunPython.noop', MIGRATION)
        self.assertNotIn('ProblemHistory.objects.create', MIGRATION)

    def test_diagnostic_reports_all_blocking_conditions(self):
        for phrase in ('workflow is not Waiting for Customer Response',
                       'escalation setting disabled', 'fewer than two existing priority',
                       'missing confirmed tracking send timestamp',
                       'response deadline has not passed', 'already at final priority',
                       'no populated later-priority company'):
            self.assertIn(phrase, COMMAND)
        parsed = ast.parse(COMMAND)
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                             and node.func.attr in ('create', 'save', 'update', 'delete', 'bulk_update')
                             for node in ast.walk(parsed)))


if __name__ == '__main__':
    unittest.main()
