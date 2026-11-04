"""Dependency-free checks for displaying old and new escalation reasons."""
import unittest
from pathlib import Path
import importlib.util

p = Path(__file__).with_name('client_email_escalation_reason.py')
spec = importlib.util.spec_from_file_location('reason_formatter', p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LabelTests(unittest.TestCase):
    def test_legacy_priority_text_is_replaced_with_field_names(self):
        old = ('[Dependency Field Priority 1 — End User] has not responded for a while. '
               'The client contact email field has been changed to '
               '[Dependency Field Priority 2 — Distributor]. Please resend the tracking link.')
        self.assertEqual(module.display_escalation_reason(old),
                         'End User has not responded for a while. '
                         'The client contact email field has been changed to '
                         'Distributor. Please resend the tracking link.')
    def test_new_reason_kept(self):
        msg = 'End User has not responded for a while. Please resend the tracking link.'
        self.assertEqual(module.display_escalation_reason(msg), msg)
    def test_custom_field_names(self):
        self.assertEqual(module.display_escalation_reason('[Dependency Field Priority 3 — Customer Account]'), 'Customer Account')
    def test_null_reason(self):
        self.assertEqual(module.display_escalation_reason(None), '')

if __name__ == '__main__':
    unittest.main()
