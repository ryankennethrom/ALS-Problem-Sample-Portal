"""Test legacy tracking-email attribution with the real scoring function (no Django required)."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

source = Path(__file__).with_name('client_email_escalation.py')
tree = ast.parse(source.read_text())
inference_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == '_infer_legacy_priority')
context = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[inference_fn], type_ignores=[])),
             str(source), 'exec'), context)
infer = context['_infer_legacy_priority']


class LegacyEmailMatchCountTests(unittest.TestCase):
    def estimate(self, saved, lists, companies=('A', 'B', 'C')):
        deps = [SimpleNamespace(field_key=f'company-{index}', name=f'Priority {index + 1}')
                for index in range(len(companies))]
        values = {dep.field_key: name for dep, name in zip(deps, companies)}
        values['contact'] = saved
        return infer(deps, values, 'contact', emails_for_company=lambda c: lists.get(c, []))

    def test_highest_overlap_wins_even_if_saved_emails_not_a_subset(self):
        result = self.estimate(['one@ex.com', 'two@ex.com', 'third@ex.com'],
                               {'A': ['one@ex.com'],
                                'B': ['ONE@ex.com', 'two@ex.com', 'other@ex.com'],
                                'C': ['third@ex.com']})
        self.assertEqual(result, (1, True))

    def test_duplicate_emails_are_counted_once_and_case_insensitive(self):
        self.assertEqual(self.estimate(['ONE@ex.com', 'one@ex.com', ' Two@ex.com '],
                                       {'A': ['one@ex.com'], 'B': ['one@ex.com', 'two@ex.com']}),
                         (1, True))

    def test_tie_including_priority_one_defaults_to_priority_one(self):
        self.assertEqual(self.estimate(['one@ex.com'],
                                       {'A': ['one@ex.com'], 'B': ['one@ex.com']}),
                         (0, False))

    def test_tie_between_later_priorities_defaults_to_populated_priority_one(self):
        self.assertEqual(self.estimate(['one@ex.com', 'two@ex.com'],
                                       {'A': ['unmatched@ex.com'],
                                        'B': ['one@ex.com'], 'C': ['two@ex.com']}),
                         (0, False))

    def test_empty_priority_one_is_ignored_in_tie(self):
        self.assertEqual(self.estimate(['one@ex.com'],
                                       {'A': [], 'B': ['one@ex.com'], 'C': ['one@ex.com']}),
                         (1, False))

    def test_empty_company_value_is_ignored_in_tie(self):
        self.assertEqual(self.estimate(['one@ex.com'],
                                       {'A': ['one@ex.com'], 'B': ['one@ex.com'], 'C': ['one@ex.com']},
                                       companies=('', 'B', 'C')),
                         (1, False))

    def test_empty_customer_export_list_cannot_win_zero_match_tie(self):
        self.assertEqual(self.estimate(['unknown@ex.com'],
                                       {'A': [], 'B': ['other@ex.com'], 'C': []}),
                         (1, False))

    def test_zero_matches_uses_priority_one_if_populated(self):
        self.assertEqual(self.estimate(['unknown@ex.com'],
                                       {'A': ['a@ex.com'], 'B': ['b@ex.com'], 'C': ['c@ex.com']}),
                         (0, False))

    def test_no_saved_emails_returns_no_attribution(self):
        self.assertEqual(self.estimate([], {'A': ['a@ex.com'], 'B': ['b@ex.com']}),
                         (None, False))

    def test_all_empty_dependencies_returns_no_attribution(self):
        self.assertEqual(self.estimate(['one@ex.com'], {'A': [], 'B': [], 'C': []}),
                         (None, False))

    def test_comma_separated_legacy_string_supported(self):
        self.assertEqual(self.estimate('one@ex.com; TWO@ex.com',
                                       {'A': ['one@ex.com'], 'B': ['one@ex.com', 'two@ex.com']}),
                         (1, True))


if __name__ == '__main__':
    unittest.main()
