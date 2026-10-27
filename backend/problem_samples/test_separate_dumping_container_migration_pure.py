"""Run with `python -m unittest problem_samples.test_separate_dumping_container_migration_pure`.

Exercise the actual migration functions with fake database querysets; Django is
not needed for this test. This does not replace a real migration on PostgreSQL.
"""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

MIGRATION = Path(__file__).parent / 'migrations' / '0096_separate_dumping_container_numbers.py'


def functions():
    code = ast.parse(MIGRATION.read_text())
    wanted = {'_old_id', '_new_id', '_update_history', 'renumber_dumping_containers'}
    nodes = [node for node in code.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    context = {'Max': lambda value: value}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MIGRATION), 'exec'), context)
    return context


class Row(SimpleNamespace):
    def save(self, update_fields=None):
        self.saved = getattr(self, 'saved', []) + [tuple(update_fields or [])]


class Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def using(self, db):
        return self

    def values_list(self, *names):
        return [tuple(getattr(row, n) for n in names) for row in self.rows]

    def filter(self, **kwargs):
        def matches(row):
            for key, expected in kwargs.items():
                if key.endswith('__isnull'):
                    if (getattr(row, key[:-8] + '_id', None) is None) != expected:
                        return False
                elif key.endswith('__in'):
                    if getattr(row, key[:-4]) not in expected:
                        return False
                elif getattr(row, key + '_id', object()) == expected if key == 'lab' else getattr(row, key) == expected:
                    continue
                else:
                    return False
            return True
        return Query(row for row in self.rows if matches(row))

    def order_by(self, *fields):
        return Query(sorted(self.rows, key=lambda row: tuple(getattr(row, f) for f in fields)))

    def aggregate(self, **fields):
        return {key: max((getattr(row, field) or 0 for row in self.rows), default=0) for key, field in fields.items()}

    def get(self, **kwargs):
        results = self.filter(**kwargs).rows
        assert len(results) == 1, (kwargs, results)
        return results[0]

    def iterator(self):
        return iter(self.rows)

    def __iter__(self):
        return iter(self.rows)


class Apps:
    def __init__(self, labs, containers, histories):
        self.mapping = {
            ('accounts', 'Lab'): SimpleNamespace(objects=Query(labs)),
            ('problem_samples', 'ProblemContainer'): SimpleNamespace(objects=Query(containers)),
            ('problem_samples', 'ProblemHistory'): SimpleNamespace(objects=Query(histories)),
        }

    def get_model(self, app, model):
        return self.mapping[(app, model)]


class DumpingMigrationTests(unittest.TestCase):
    def setUp(self):
        self.f = functions()
        self.edm = Row(pk=1, id=1, code='EDM', next_container_number=12, next_dumping_container_number=1)
        self.cgy = Row(pk=2, id=2, code='CGY', next_container_number=2, next_dumping_container_number=1)
        self.physical_a = Row(pk=5, lab_id=1, lab_number=5, is_dumping=False, created_at=1)
        self.physical_b = Row(pk=10, lab_id=1, lab_number=10, is_dumping=False, created_at=4)
        self.dump_one = Row(pk=6, lab_id=1, lab_number=6, is_dumping=True, created_at=2, dumped_sample_ids=['ticket-a'])
        self.dump_two = Row(pk=9, lab_id=1, lab_number=9, is_dumping=True, created_at=3, dumped_sample_ids=['ticket-b'])
        self.dump_other = Row(pk=2, lab_id=2, lab_number=2, is_dumping=True, created_at=4, dumped_sample_ids=['ticket-c'])
        self.history_transfer = Row(problem_id='ticket-a', summary='Container EDM PC-00005 disposed into EDM PC-00006', details={
            'changes': [{'field': 'Container ID', 'before': 'EDM PC-00005', 'after': 'EDM PC-00006'}],
            'source_container_id': 'EDM PC-00005',
            'dumping_container_id': 'EDM PC-00006',
            'reason': 'Operator requested disposal',
        })
        self.history_undo = Row(problem_id='ticket-b', summary='Container EDM PC-00009 disposal undone', details={
            'changes': [{'field': 'Container ID', 'before': 'EDM PC-00009', 'after': 'EDM PC-00010'}],
        })
        self.history_unrelated = Row(problem_id='ticket-a', summary='New note', details={
            'changes': [{'field': 'Customer name', 'after': 'EDM PC-00006'}],
            'reason': 'EDM PC-00006 is written on old paperwork',
        })
        self.apps = Apps([self.edm, self.cgy],
                         [self.physical_a, self.dump_two, self.dump_one, self.physical_b, self.dump_other],
                         [self.history_transfer, self.history_undo, self.history_unrelated])

    def migrate(self):
        self.f['renumber_dumping_containers'](self.apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))

    def test_renumbers_dumping_separately_and_preserves_physical_ids(self):
        self.migrate()
        self.assertEqual((self.physical_a.lab_number, self.physical_b.lab_number), (5, 10))
        self.assertEqual((self.dump_one.lab_number, self.dump_two.lab_number), (1, 2))
        self.assertEqual(self.dump_other.lab_number, 1)
        self.assertEqual(self.edm.next_dumping_container_number, 3)
        self.assertEqual(self.cgy.next_dumping_container_number, 2)
        self.assertEqual(self.edm.next_container_number, 12)

    def test_history_updated_and_original_id_preserved(self):
        self.migrate()
        self.assertEqual(self.history_transfer.summary, 'Container EDM PC-00005 disposed into EDM DC-00001')
        self.assertEqual(self.history_transfer.details['changes'][0]['after'], 'EDM DC-00001')
        self.assertEqual(self.history_transfer.details['changes'][0]['before'], 'EDM PC-00005')
        self.assertEqual(self.history_transfer.details['dumping_container_id'], 'EDM DC-00001')
        self.assertEqual(self.history_transfer.details['source_container_id'], 'EDM PC-00005')
        self.assertEqual(self.history_transfer.details['container_id_renames'], [
            {'before': 'EDM PC-00006', 'after': 'EDM DC-00001'},
        ])
        self.assertEqual(self.history_transfer.details['reason'], 'Operator requested disposal')

    def test_undo_history_follows_new_dumping_id(self):
        self.migrate()
        self.assertEqual(self.history_undo.summary, 'Container EDM DC-00002 disposal undone')
        self.assertEqual(self.history_undo.details['changes'][0]['before'], 'EDM DC-00002')
        self.assertEqual(self.history_undo.details['changes'][0]['after'], 'EDM PC-00010')

    def test_unrelated_customer_notes_and_audit_not_changed(self):
        self.migrate()
        self.assertEqual(self.history_unrelated.summary, 'New note')
        self.assertEqual(self.history_unrelated.details['changes'][0]['after'], 'EDM PC-00006')
        self.assertEqual(self.history_unrelated.details['reason'], 'EDM PC-00006 is written on old paperwork')
        self.assertFalse(getattr(self.history_unrelated, 'saved', None))

    def test_counter_corrected_if_existing_physical_sequence_higher(self):
        self.edm.next_container_number = 2
        self.migrate()
        self.assertEqual(self.edm.next_container_number, 11)

    def test_legacy_labless_dumping_container_history_updated(self):
        legacy = Row(pk=83, lab_id=None, lab_number=None, is_dumping=True, created_at=3,
                     dumped_sample_ids=['legacy-ticket'])
        history = Row(problem_id='legacy-ticket', summary='Dumping container PC-000083 restored',
                      details={'changes': [{'field': 'Container ID', 'before': 'PC-000083', 'after': 'PC-000084'}]})
        self.apps.mapping[('problem_samples', 'ProblemContainer')].objects.rows.append(legacy)
        self.apps.mapping[('problem_samples', 'ProblemHistory')].objects.rows.append(history)
        self.migrate()
        self.assertEqual(history.summary, 'Dumping container DC-000083 restored')
        self.assertEqual(history.details['changes'][0]['before'], 'DC-000083')


if __name__ == '__main__':
    unittest.main()
