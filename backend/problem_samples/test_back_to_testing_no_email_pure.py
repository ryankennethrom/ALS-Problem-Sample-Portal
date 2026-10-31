"""Dependency-free regressions for no-email Back to Testing workflow."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name('views.py').read_text()
VIEW_TREE = ast.parse(SOURCE)
VIEW_CLASS = next(node for node in VIEW_TREE.body if isinstance(node, ast.ClassDef) and node.name == 'ProblemSampleViewSet')

def method_source(name):
    method = next(node for node in VIEW_CLASS.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    return ast.get_source_segment(SOURCE, method)

class BackToTestingNoEmailPureTests(unittest.TestCase):
    def test_single_ticket_saves_without_email_fields(self):
        method = method_source('perform_update')
        self.assertIn('serializer.save(', method)
        self.assertNotIn('back_to_testing_email_sent', method)
        self.assertNotIn('back_to_testing_email_body', method)
        self.assertNotIn('back_to_testing_not_sent_reason', method)

    def test_bulk_endpoint_does_not_require_notification_confirmation(self):
        method = method_source('bulk_back_to_testing')
        self.assertIn('PROBLEM_STATUS_BACK_TO_TESTING', method)
        self.assertNotIn('back_to_testing_email_sent', method)
        self.assertNotIn('back_to_testing_email_body', method)
        self.assertNotIn('email_batch_id', method)
        self.assertNotIn('emails_sent_confirmed', method)

    def test_bulk_endpoint_keeps_role_restrictions(self):
        method = method_source('bulk_back_to_testing')
        self.assertIn("profile.role == 'customer_service'", method)
        self.assertIn('HTTP_403_FORBIDDEN', method)

    def test_bulk_endpoint_keeps_history_and_container_checks(self):
        method = method_source('bulk_back_to_testing')
        self.assertIn('disposed_at', method)
        self.assertIn("summary='Moved back to testing'", method)
        self.assertIn('sample.container = None', method)

    def test_legacy_email_notification_endpoint_is_removed(self):
        self.assertNotIn('def back_to_testing_notification(', SOURCE)
        self.assertNotIn("'back_to_testing'", method_source('email_not_sent'))

    def test_customer_tracking_email_not_sent_endpoint_still_works(self):
        method = method_source('email_not_sent')
        self.assertIn("kind != 'customer'", method)
        self.assertIn('pending_tracking_token', method)

if __name__ == '__main__':
    unittest.main()
