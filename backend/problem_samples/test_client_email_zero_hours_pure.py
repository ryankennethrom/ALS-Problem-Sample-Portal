"""Dependency-free checks for immediate Client Email priority escalation."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).parent
MIGRATION = ROOT / 'migrations' / '0104_allow_zero_client_email_fallback_hours.py'


class ZeroHourConfigurationTests(unittest.TestCase):
    def test_api_accepts_zero_but_rejects_invalid_values(self):
        source = (ROOT / 'serializers.py').read_text()
        self.assertIn('type(hours) is not int or not 0 <= hours <= 87600', source)
        self.assertIn('Enter 0 to 87,600 hours.', source)

    def test_model_validator_accepts_zero(self):
        source = (ROOT / 'models.py').read_text()
        self.assertIn('validators=[MinValueValidator(0), MaxValueValidator(87600)]', source)

    def test_migration_updates_validator_and_depends_on_0103(self):
        source = MIGRATION.read_text()
        tree = ast.parse(source)
        self.assertTrue(tree)
        self.assertIn("('problem_samples', '0103_reconcile_legacy_tracking_send_history')", source)
        self.assertIn('migrations.AlterField(', source)
        self.assertIn('MinValueValidator(0)', source)
        self.assertNotIn('migrations.RunPython', source)

    def test_scheduler_does_not_treat_zero_as_disabled(self):
        source = (ROOT / 'client_email_escalation.py').read_text()
        self.assertIn('client_email_fallback_hours__isnull=False', source)
        self.assertIn('timedelta(hours=minimum_hours)', source)
        self.assertIn('now < anchor + timedelta(hours=column.client_email_fallback_hours)', source)


if __name__ == '__main__':
    unittest.main()
