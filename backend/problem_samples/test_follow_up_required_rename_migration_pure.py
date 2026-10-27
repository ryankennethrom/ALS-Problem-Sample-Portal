"""Dependency-free checks of migration 0095's data transformation.

Run: python -m unittest problem_samples.test_follow_up_required_rename_migration_pure
Run from the backend directory. These tests use the migration's actual functions,
extracted without importing Django, and fake in-memory model managers.
"""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


MIGRATION = Path(__file__).parent / 'migrations' / '0095_rename_cs_follow_up_workflow.py'


def migration_functions():
    syntax = ast.parse(MIGRATION.read_text())
    names = {'replace_exact', 'rename_workflow', 'forwards', 'backwards'}
    declarations = [node for node in syntax.body if isinstance(node, ast.FunctionDef) and node.name in names]
    context = {'OLD_WORKFLOW': 'CS Follow-Up', 'NEW_WORKFLOW': 'Follow Up Required', 'WORKFLOW_KEY': 'current-workflow'}
    exec(compile(ast.Module(body=declarations, type_ignores=[]), str(MIGRATION), 'exec'), context)
    return context


class Row(SimpleNamespace):
    def save(self, update_fields):
        self.saved_fields.append(tuple(update_fields))


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, **kwargs):
        return Query([row for row in self.rows if all(getattr(row, name) == value for name, value in kwargs.items())])

    def exclude(self, **kwargs):
        return Query([row for row in self.rows if not all(getattr(row, name) == value for name, value in kwargs.items())])

    def all(self):
        return self

    def only(self, *fields):
        return self

    def iterator(self):
        return iter(self.rows)

    def update(self, **values):
        for row in self.rows:
            for name, value in values.items():
                setattr(row, name, value)


class Apps:
    def __init__(self, samples, columns, containers):
        self.mapping = {
            'ProblemSample': SimpleNamespace(objects=Query(samples)),
            'ProblemColumn': SimpleNamespace(objects=Query(columns)),
            'ProblemContainer': SimpleNamespace(objects=Query(containers)),
        }

    def get_model(self, app_name, model_name):
        assert app_name == 'problem_samples'
        return self.mapping[model_name]


class RenameMigrationTests(unittest.TestCase):
    def setUp(self):
        self.functions = migration_functions()
        self.old_sample = Row(pk='one', current_workflow='CS Follow-Up', custom_values={
            'current-workflow': 'CS Follow-Up', 'other-field': 'do not modify',
        })
        self.waiting_sample = Row(pk='two', current_workflow='Waiting for Customer Response', custom_values={
            'current-workflow': 'Waiting for Customer Response',
        })
        self.workflow_column = Row(field_key='current-workflow', choices=[
            'CS Follow-Up', 'Waiting for Customer Response', 'Disposed',
        ], default_value='CS Follow-Up', description='Routing used by CS Follow-Up and shipping.',
            intercolumn_rules=[], saved_fields=[])
        self.controller_column = Row(field_key='routing-control', choices=[], default_value=None,
            description='Other field', intercolumn_rules=[{'when_other_equals': 'CS Follow-Up',
                                                            'set_controller_to': 'CS Follow-Up'}], saved_fields=[])
        self.container = Row(disposal_snapshot={
            'one': {'current_workflow': 'CS Follow-Up', 'custom_values': {
                'current-workflow': 'CS Follow-Up', 'brand': 'SampleCo'}, 'status': 'IN PROGRESS'},
            'two': {'current_workflow': 'Disposed', 'custom_values': {'current-workflow': 'Disposed'}},
        }, saved_fields=[])
        self.apps = Apps([self.old_sample, self.waiting_sample],
                         [self.workflow_column, self.controller_column], [self.container])

    def test_forward_renames_stored_ticket_and_column_metadata(self):
        self.functions['forwards'](self.apps, None)
        self.assertEqual(self.old_sample.current_workflow, 'Follow Up Required')
        self.assertEqual(self.old_sample.custom_values['current-workflow'], 'Follow Up Required')
        self.assertEqual(self.old_sample.custom_values['other-field'], 'do not modify')
        self.assertEqual(self.workflow_column.choices, [
            'Follow Up Required', 'Waiting for Customer Response', 'Disposed',
        ])
        self.assertEqual(self.workflow_column.default_value, 'Follow Up Required')
        self.assertEqual(self.workflow_column.description, 'Routing used by Follow Up Required and shipping.')

    def test_forward_updates_disposal_snapshots_and_controller_rules(self):
        self.functions['forwards'](self.apps, None)
        saved = self.container.disposal_snapshot['one']
        self.assertEqual(saved['current_workflow'], 'Follow Up Required')
        self.assertEqual(saved['custom_values']['current-workflow'], 'Follow Up Required')
        self.assertEqual(saved['custom_values']['brand'], 'SampleCo')
        self.assertEqual(self.container.disposal_snapshot['two']['current_workflow'], 'Disposed')
        self.assertEqual(self.controller_column.intercolumn_rules[0]['when_other_equals'], 'Follow Up Required')

    def test_other_workflows_remain_unchanged_and_rerun_is_idempotent(self):
        self.functions['forwards'](self.apps, None)
        initial = self.container.disposal_snapshot.copy()
        self.functions['forwards'](self.apps, None)
        self.assertEqual(self.waiting_sample.current_workflow, 'Waiting for Customer Response')
        self.assertEqual(self.container.disposal_snapshot, initial)
        self.assertEqual(self.workflow_column.choices.count('Follow Up Required'), 1)

    def test_reverse_restores_previous_workflow_values(self):
        self.functions['forwards'](self.apps, None)
        self.functions['backwards'](self.apps, None)
        self.assertEqual(self.old_sample.current_workflow, 'CS Follow-Up')
        self.assertEqual(self.old_sample.custom_values['current-workflow'], 'CS Follow-Up')
        self.assertEqual(self.workflow_column.default_value, 'CS Follow-Up')
        self.assertIn('CS Follow-Up', self.workflow_column.choices)
        self.assertEqual(self.container.disposal_snapshot['one']['current_workflow'], 'CS Follow-Up')
        self.assertEqual(self.controller_column.intercolumn_rules[0]['set_controller_to'], 'CS Follow-Up')


if __name__ == '__main__':
    unittest.main()
