"""Dependency-free tests that execute the refresh handler and inspect its ORM filter."""
import ast
import builtins
from contextlib import nullcontext
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).parent
VIEWS = ast.parse((ROOT / 'system_email_views.py').read_text())
ESCALATION = ast.parse((ROOT / 'client_email_escalation.py').read_text())


def extracted_function(tree, name, *, class_name=None):
    children = next(node.body for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name) if class_name else tree.body
    fn = next(node for node in children if isinstance(node, ast.FunctionDef) and node.name == name)
    return compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), '<actual source>', 'exec')


class RefreshEndpointTests(unittest.TestCase):
    def execute(self, fail_monthly=False, fail_escalation=False):
        events = []

        def monthly():
            events.append('monthly')
            if fail_monthly:
                raise RuntimeError('sample monthly failure')

        def escalation():
            events.append('escalation')
            if fail_escalation:
                raise RuntimeError('sample escalation failure')

        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'client_email_escalation' and level == 1:
                return SimpleNamespace(check_client_email_escalations_on_request=escalation)
            return original_import(name, globals, locals, fromlist, level)

        env = {
            '__builtins__': dict(vars(builtins), __import__=fake_import),
            'check_monthly_reports_on_app_refresh': monthly,
            'Response': lambda data, status=200: (status, data),
            'logger': SimpleNamespace(exception=lambda msg: events.append('log: ' + msg)),
        }
        exec(extracted_function(VIEWS, 'post', class_name='QueueMonthlyReportsOnRefreshView'), env)
        return env['post'](None, None), events

    def test_both_checks_execute_and_report_success(self):
        response, events = self.execute()
        self.assertEqual(response, (200, {'ok': True, 'monthly_reports_checked': True,
                                          'client_email_escalations_checked': True}))
        self.assertEqual(events, ['monthly', 'escalation'])

    def test_monthly_exception_does_not_block_escalation(self):
        (status, data), events = self.execute(fail_monthly=True)
        self.assertEqual(status, 200)
        self.assertTrue(data['ok'])
        self.assertFalse(data['monthly_reports_checked'])
        self.assertTrue(data['client_email_escalations_checked'])
        self.assertIn('escalation', events)
        self.assertTrue(any(item.startswith('log: ') for item in events))

    def test_escalation_exception_is_not_silently_reported_as_success(self):
        (status, data), events = self.execute(fail_escalation=True)
        self.assertEqual(status, 200)
        self.assertTrue(data['monthly_reports_checked'])
        self.assertFalse(data['client_email_escalations_checked'])
        self.assertIn('monthly', events)
        self.assertTrue(any(item.startswith('log: ') for item in events))

    def test_total_failure_has_non_success_http_status(self):
        (status, data), events = self.execute(fail_monthly=True, fail_escalation=True)
        self.assertEqual(status, 503)
        self.assertIn('Automatic refresh checks failed', data['detail'])
        self.assertEqual(events.count('monthly'), 1)
        self.assertEqual(events.count('escalation'), 1)


class EscalationQueryTests(unittest.TestCase):
    def test_query_checks_indexed_and_legacy_json_workflows(self):
        collected = []

        class FakeQ:
            def __init__(self, **kwargs):
                self.conditions = [kwargs]
            def __or__(self, other):
                combined = FakeQ()
                combined.conditions = self.conditions + other.conditions
                return combined

        class FakeRows:
            def filter(self, *args, **kwargs):
                collected.extend(args)
                collected.append(kwargs)
                return self
            def values_list(self, *args, **kwargs):
                return []

        column = SimpleNamespace(id=12, table_id=2, client_email_fallback_hours=1,
                                 ordered_client_email_dependency_columns=lambda: [])
        env = {
            'Q': FakeQ,
            'ProblemColumn': SimpleNamespace(TYPE_CLIENT_EMAIL='client_email', objects=SimpleNamespace(filter=lambda **kw: [column])),
            'ProblemSample': SimpleNamespace(objects=FakeRows()),
            'CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER': 'Waiting for Customer Response',
            'SYSTEM_CURRENT_WORKFLOW_FIELD_KEY': 'current-workflow',
            'timezone': SimpleNamespace(now=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc)),
            'timedelta': timedelta,
        }
        exec(extracted_function(ESCALATION, 'transition_due_client_email_priorities'), env)
        self.assertEqual(env['transition_due_client_email_priorities'](), 0)
        conditions = [item for q in collected if isinstance(q, FakeQ) for item in q.conditions]
        self.assertIn({'current_workflow': 'Waiting for Customer Response'}, conditions)
        self.assertIn({'custom_values__current-workflow': 'Waiting for Customer Response'}, conditions)
        self.assertTrue(any('client_email_last_tracking_sent_at__lte' in item for item in collected if isinstance(item, dict)))

    def test_due_ticket_locks_only_ticket_row_without_nullable_table_join(self):
        """Regression: PostgreSQL rejects FOR UPDATE on nullable join sides."""
        events = []
        ticket = SimpleNamespace(table_id=2)

        class FakeQ:
            def __init__(self, **kwargs):
                self.conditions = [kwargs]
            def __or__(self, other):
                combined = FakeQ()
                combined.conditions = self.conditions + other.conditions
                return combined

        class FakeRows:
            def filter(self, *args, **kwargs):
                return self
            def values_list(self, *args, **kwargs):
                return [56]
            def select_for_update(self, *args, **kwargs):
                events.append(('lock', kwargs))
                if kwargs.get('of') != ('self',):
                    raise AssertionError('Must lock only the ticket row')
                return self
            def select_related(self, *args, **kwargs):
                raise AssertionError('Nullable table join causes PostgreSQL FOR UPDATE failure')
            def first(self):
                return ticket

        column = SimpleNamespace(id=12, table_id=2, client_email_fallback_hours=1,
                                 ordered_client_email_dependency_columns=lambda: [])
        env = {
            'Q': FakeQ,
            'ProblemColumn': SimpleNamespace(TYPE_CLIENT_EMAIL='client_email', objects=SimpleNamespace(filter=lambda **kw: [column])),
            'ProblemSample': SimpleNamespace(objects=FakeRows()),
            'CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER': 'Waiting for Customer Response',
            'SYSTEM_CURRENT_WORKFLOW_FIELD_KEY': 'current-workflow',
            'timezone': SimpleNamespace(now=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc)),
            'timedelta': timedelta,
            'transaction': SimpleNamespace(atomic=nullcontext),
            'try_escalate_ticket': lambda value, **kwargs: value is ticket,
        }
        exec(extracted_function(ESCALATION, 'transition_due_client_email_priorities'), env)
        self.assertEqual(env['transition_due_client_email_priorities'](), 1)
        self.assertEqual(events, [('lock', {'of': ('self',)})])

    def test_diagnostic_calls_out_legacy_workflow_index_mismatch(self):
        source = (ROOT / 'management/commands/diagnose_client_email_escalation.py').read_text()
        self.assertIn('ticket.current_workflow != ticket.workflow_status', source)
        self.assertIn('Workflow index differs', source)


if __name__ == '__main__':
    unittest.main()
