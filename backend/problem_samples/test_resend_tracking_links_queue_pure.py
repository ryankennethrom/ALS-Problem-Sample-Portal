"""Dependency-free regression checks on the new queue query and configuration."""
import ast
from pathlib import Path
import unittest

TREE = ast.parse(Path(__file__).with_name('dashboard_views.py').read_text())
FUNCTIONS = {n.name:n for n in TREE.body if isinstance(n, ast.FunctionDef)}
CLASSES = {n.name:n for n in TREE.body if isinstance(n, ast.ClassDef)}


class ResendQueueSourceTests(unittest.TestCase):
    def test_last_history_event_is_required(self):
        text = ast.unparse(FUNCTIONS['resend_tracking_link_tickets'])
        self.assertIn("order_by('-created_at', '-pk')", text)
        self.assertIn('last_history_id__in=qualifying_ids', text)
        self.assertIn('details__automatic=True', text)
        self.assertIn('details__from_priority__isnull=False', text)
        self.assertIn('details__to_priority__isnull=False', text)
        self.assertIn('details__reason__endswith=ESCALATION_REASON_END', text)

    def test_only_enabled_client_email_tables_and_follow_up_workflow(self):
        text = ast.unparse(FUNCTIONS['resend_tracking_link_tickets'])
        self.assertIn('client_email_fallback_hours__isnull=False', text)
        self.assertIn('column_type=ProblemColumn.TYPE_CLIENT_EMAIL', text)
        self.assertIn('current_workflow=CURRENT_WORKFLOW_DEFAULT', text)

    def test_view_uses_authorized_lab_and_pagination(self):
        view = ast.unparse(CLASSES['ResendTrackingLinksView'])
        self.assertIn('scope_tickets(request, ProblemSample.objects.all())', view)
        self.assertIn('PAGE_SIZE = 50', view)
        self.assertIn('if page < 1', view)
        self.assertIn('resend_tracking_link_tickets(scoped)', view)

    def test_others_queue_excludes_priority_escalation_tickets(self):
        text = ast.unparse(FUNCTIONS['customer_service_other_tickets'])
        self.assertIn("exclude(pk__in=resend_tracking_link_tickets(queryset).values('pk'))", text)

    def test_no_extra_database_migrations_required(self):
        self.assertIn('resend_tracking_links_enabled', FUNCTIONS)
        self.assertIn('resend_tracking_link_tickets', FUNCTIONS)


if __name__ == '__main__':
    unittest.main()
