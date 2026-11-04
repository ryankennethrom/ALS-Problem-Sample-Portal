"""Dependency-free checks for the Action Required pending-email snapshot and row."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name('dashboard_views.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
SNAPSHOT = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'action_required_snapshot')
VIEW = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'ActionRequiredEmailPreviewView')
POST = next(node for node in VIEW.body if isinstance(node, ast.FunctionDef) and node.name == 'post')


class FakeQuerySet:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, **criteria):
        return FakeQuerySet([row for row in self.rows if all(row[key] == value for key, value in criteria.items())])

    def count(self):
        return len(self.rows)


class PendingEmailSnapshotTests(unittest.TestCase):
    def test_pending_count_only_includes_unsent_messages_in_selected_lab(self):
        """Execute the actual filtering/count AST with a minimal model stand-in."""
        assignments = []
        for node in SNAPSHOT.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                and t.value.id == 'counts' and isinstance(t.slice, ast.Constant)
                and t.slice.value == 'pending_system_emails' for t in node.targets
            ):
                index = SNAPSHOT.body.index(node)
                # Include pending_emails assignment, lab filtering, and count.
                assignments = SNAPSHOT.body[index - 2:index + 1]
                break
        self.assertEqual(len(assignments), 3)
        code = compile(ast.fix_missing_locations(ast.Module(body=assignments, type_ignores=[])), '<dashboard snapshot>', 'exec')

        class FakeEmail:
            STATUS_PENDING = 'pending'
            objects = FakeQuerySet([
                {'status': 'pending', 'lab': 'EDM'},
                {'status': 'pending', 'lab': 'YYC'},
                {'status': 'sent', 'lab': 'EDM'},
                {'status': 'pending', 'lab': 'EDM'},
            ])

        for lab, expected in [('EDM', 2), ('YYC', 1), (None, 3)]:
            values = {'SystemEmail': FakeEmail, 'lab': lab, 'counts': {}}
            exec(code, values)
            self.assertEqual(values['counts']['pending_system_emails'], expected)

    def test_pending_count_is_included_in_email_snapshot_with_correct_queue_link(self):
        rows = next(node.value for node in POST.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'rows' for target in node.targets))
        items = ast.literal_eval(rows)
        self.assertEqual(items[0], (
            'Pending System Emails', 'pending_system_emails', '/send-system-emails#pending-system-emails'
        ))
        self.assertEqual(len({key for _, key, _ in items}), len(items))


if __name__ == '__main__':
    unittest.main()
