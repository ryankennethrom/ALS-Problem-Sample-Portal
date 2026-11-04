"""Dependency-free runtime checks for the actual app-refresh scheduler function."""
import ast
from datetime import date
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name('system_email_service.py')
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
FUNC = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
            and node.name == 'check_monthly_reports_on_app_refresh')
CODE = compile(ast.fix_missing_locations(ast.Module(body=[FUNC], type_ignores=[])), str(SOURCE), 'exec')


class FakeCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def add(self, key, value, timeout):
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def set(self, key, value, timeout):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


class RefreshCheckTests(unittest.TestCase):
    def setup_check(self, callback):
        cache = FakeCache()
        env = {
            'cache': cache,
            'previous_month': lambda: (date(2026, 10, 1), date(2026, 11, 1)),
            'queue_due_monthly_reports': callback,
        }
        exec(CODE, env)
        return env['check_monthly_reports_on_app_refresh'], cache

    def test_first_refresh_queues_once_and_repeated_refreshes_are_throttled(self):
        runs = []
        check, cache = self.setup_check(lambda: runs.append('called') or {'created': 3})
        self.assertEqual(check()['created'], 3)
        self.assertEqual(check(), {'checked': False})
        self.assertEqual(runs, ['called'])
        self.assertFalse(any('running' in key for key in cache.values))

    def test_check_retries_after_cooldown(self):
        runs = []
        check, cache = self.setup_check(lambda: runs.append('called') or {'created': 0})
        check()
        cache.values.clear()  # Simulate cache expiry after 5 minutes.
        self.assertTrue(check()['checked'])
        self.assertEqual(len(runs), 2)

    def test_failure_does_not_suppress_next_attempt(self):
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('database temporarily unavailable')
            return {'created': 1}
        check, cache = self.setup_check(flaky)
        with self.assertRaisesRegex(RuntimeError, 'database temporarily unavailable'):
            check()
        self.assertFalse(cache.values)
        self.assertEqual(check()['created'], 1)

    def test_concurrent_refresh_skips_while_check_in_progress(self):
        check, cache = self.setup_check(lambda: {'created': 1})
        cache.values['monthly-report-refresh:running:2026-10-01'] = True
        self.assertEqual(check(), {'checked': False})


if __name__ == '__main__':
    unittest.main()
