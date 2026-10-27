"""Dependency-free tests for the PC allocator and targeted legacy recovery.

Run: python -m unittest problem_samples.test_container_gap_allocation_pure
"""
import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parent


def load_func(path, function_name, namespace=None):
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name)
    scope = dict(namespace or {})
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), scope)
    return scope[function_name]


class FakeTicketSet:
    def __init__(self, count):
        self.count = count

    def using(self, db):
        return self

    def exists(self):
        return bool(self.count)


class FakeContainer(SimpleNamespace):
    def save(self, **kwargs):
        self.saved = kwargs


class FakeContainerQuery:
    def __init__(self, record):
        self.record = record

    def using(self, db):
        return self

    def filter(self, **kwargs):
        if not self.record or self.record.lab_code.upper() != kwargs['lab__code__iexact'].upper():
            self.record = None
        elif (self.record.lab_number != kwargs['lab_number'] or
              self.record.is_dumping != kwargs['is_dumping'] or
              (self.record.disposed_at is None) != kwargs['disposed_at__isnull']):
            self.record = None
        return self

    def first(self):
        return self.record


class ContainerGapTests(unittest.TestCase):
    def setUp(self):
        self.find_gap = load_func(ROOT / 'labs.py', 'first_available_number')
        self.archive = load_func(ROOT / 'labs.py', 'archive_legacy_empty_disposal')
        self.reopen = load_func(ROOT / 'migrations/0097_reactivate_empty_edmonton_pc_00003.py',
                                'reactivate_edmonton_pc_00003', {'timezone': SimpleNamespace(now=lambda: datetime(2026, 10, 27, tzinfo=timezone.utc))})

    def test_gaps_in_physical_numbers_are_filled(self):
        self.assertEqual(self.find_gap([1, 2, 4, 7, 8]), 3)
        self.assertEqual(self.find_gap([1, 2, 3, 7, 8]), 4)

    def test_contiguous_numbers_take_next(self):
        self.assertEqual(self.find_gap([1, 2, 3]), 4)
        self.assertEqual(self.find_gap([]), 1)

    def test_deduplicates_or_ignores_null_and_zero_values(self):
        self.assertEqual(self.find_gap([None, 0, 1, 1, 2, 5]), 3)

    def test_archives_disposed_state_before_reactivation(self):
        previous = datetime(2026, 10, 5, tzinfo=timezone.utc)
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        box = FakeContainer(disposed_at=previous, disposed_by_id=19,
                            disposal_snapshot={'some-ticket': {'current_workflow': 'Disposed'}})
        self.archive(box, reopened_at=now, reopened_by_id=14, reason='Safe to reuse')
        self.assertIsNone(box.disposed_at)
        self.assertIsNone(box.disposed_by)
        self.assertEqual(box.disposal_snapshot['some-ticket']['current_workflow'], 'Disposed')
        audit = box.disposal_snapshot['_legacy_reactivation_events'][0]
        self.assertEqual(audit['disposed_by_id'], 19)
        self.assertEqual(audit['reactivated_by_id'], 14)
        self.assertEqual(audit['reason'], 'Safe to reuse')

    def migration_container(self, *, lab='EDM', number=3, count=0, dumped=False, disposed=True):
        return FakeContainer(lab_code=lab, lab_number=number, is_dumping=dumped,
                             disposed_at=datetime(2026, 10, 5, tzinfo=timezone.utc) if disposed else None,
                             disposed_by_id=11, disposal_snapshot={'old': {'state': 'prior'}},
                             problem_samples=FakeTicketSet(count))

    def migrate(self, record):
        apps = SimpleNamespace(get_model=lambda app, name: SimpleNamespace(objects=FakeContainerQuery(record)))
        self.reopen(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))

    def test_migration_reopens_only_edm_pc_00003_when_empty(self):
        box = self.migration_container()
        self.migrate(box)
        self.assertIsNone(box.disposed_at)
        self.assertEqual(box.disposal_snapshot['old'], {'state': 'prior'})
        self.assertEqual(box.disposal_snapshot['_legacy_reactivation_events'][0]['disposed_by_id'], 11)

    def test_migration_skips_assigned_container(self):
        box = self.migration_container(count=1)
        self.migrate(box)
        self.assertIsNotNone(box.disposed_at)

    def test_migration_skips_other_containers_and_dumping(self):
        for kwargs in ({'lab': 'CGY'}, {'number': 4}, {'dumped': True}, {'disposed': False}):
            with self.subTest(kwargs=kwargs):
                box = self.migration_container(**kwargs)
                self.migrate(box)
                self.assertEqual(box.disposed_at is None, not kwargs.get('disposed', True))


if __name__ == '__main__':
    unittest.main()
