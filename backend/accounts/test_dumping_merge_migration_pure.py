"""No-Django regression tests for the accounts migration-branch merge."""

import ast
import unittest
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / 'migrations'
SAMPLES_MIGRATIONS = MIGRATIONS.parent.parent / 'problem_samples' / 'migrations'


def _migration_field(filename, field):
    tree = ast.parse(filename.read_text(encoding='utf-8'))
    migration = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Migration')
    assignment = next(node for node in migration.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == field for t in node.targets))
    return ast.literal_eval(assignment.value)


class DumpingMigrationMergeTests(unittest.TestCase):
    def test_merge_depends_on_both_existing_accounts_branches(self):
        self.assertEqual(
            _migration_field(MIGRATIONS / '0009_merge_lab_id_and_dumping_counter.py', 'dependencies'),
            [('accounts', '0008_alter_lab_id'), ('accounts', '0008_next_dumping_container_number')],
        )

    def test_merge_has_no_database_or_data_operations(self):
        self.assertEqual(_migration_field(MIGRATIONS / '0009_merge_lab_id_and_dumping_counter.py', 'operations'), [])

    def test_dumping_renumbering_waits_for_accounts_merge(self):
        deps = _migration_field(SAMPLES_MIGRATIONS / '0096_separate_dumping_container_numbers.py', 'dependencies')
        self.assertIn(('accounts', '0009_merge_lab_id_and_dumping_counter'), deps)
        self.assertIn(('problem_samples', '0095_rename_cs_follow_up_workflow'), deps)
        self.assertNotIn(('accounts', '0008_next_dumping_container_number'), deps)

    def test_existing_dumping_counter_branch_is_preserved(self):
        deps = _migration_field(MIGRATIONS / '0008_next_dumping_container_number.py', 'dependencies')
        self.assertEqual(deps, [('accounts', '0007_lab')])


if __name__ == '__main__':
    unittest.main()
