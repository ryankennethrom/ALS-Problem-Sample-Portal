"""Dependency-free matching checks. Django/DB integration tests live in test_distributor_cc_rules.py."""
import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).with_name('brand_email_rules.py').read_text()
NODES = ast.parse(SOURCE)
FUNCTIONS = [node for node in NODES.body if isinstance(node, ast.FunctionDef)]


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, **conditions):
        return FakeQuery([row for row in self.rows if all(
            str(getattr(row, key.removesuffix('__iexact'), '')).casefold() == str(value).casefold()
            for key, value in conditions.items())])

    def exclude(self, **conditions):
        return FakeQuery([row for row in self.rows if not all(getattr(row, key) == value for key, value in conditions.items())])

    def values_list(self, field, flat=False):
        assert flat
        return [getattr(row, field) for row in self.rows]


class FakeTable:
    def __init__(self, columns):
        self.columns = SimpleNamespace(all=lambda: columns)


class BrandEmailRulePureTests(unittest.TestCase):
    def setUp(self):
        globals_for_exec = {
            're': re,
            'Customer': SimpleNamespace(objects=FakeQuery([
                SimpleNamespace(company_name='Acme Supply', customer_type='Distributor', brand='Northstar'),
                SimpleNamespace(company_name='Acme Supply', customer_type='End User', brand='Wrong Type'),
                SimpleNamespace(company_name='Final Customer', customer_type='End User', brand='NORTHSTAR PLUS'),
            ])),
            'ProblemColumn': SimpleNamespace(TYPE_BRAND='brand', TYPE_DISTRIBUTOR='distributor', TYPE_END_USER='end_user'),
        }
        exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), '<brand_email_rules>', 'exec'), globals_for_exec)
        self.funcs = globals_for_exec
        self.distributor = SimpleNamespace(pk='distributor-id', field_key='dist', column_type='distributor')
        self.end_user = SimpleNamespace(pk='end-user-id', field_key='end', column_type='end_user')
        self.brand = SimpleNamespace(pk='brand-id', field_key='brand', column_type='brand',
                                     company_brand_dependencies=['distributor-id', 'end-user-id'], brand_cc_rules=[])
        self.brand.table = FakeTable([self.brand, self.distributor, self.end_user])

    def test_exact_casefold(self):
        self.assertTrue(self.funcs['brand_matches']('nOrThStar', {'pattern':'northstar','match_type':'exact'}))

    def test_contains(self):
        self.assertTrue(self.funcs['brand_matches']('My NORTHSTAR brand', {'pattern':'northstar','match_type':'contains'}))

    def test_wildcards(self):
        fn = self.funcs['brand_matches']
        self.assertTrue(fn('NORTH STAR', {'pattern':'north*','match_type':'wildcard'}))
        self.assertTrue(fn('Brand4', {'pattern':'brand?','match_type':'wildcard'}))
        self.assertFalse(fn('Brand444', {'pattern':'brand?','match_type':'wildcard'}))

    def test_starts_and_ends(self):
        fn = self.funcs['brand_matches']
        self.assertTrue(fn('Northstar Plus', {'pattern':'north','match_type':'starts_with'}))
        self.assertTrue(fn('Northstar Plus', {'pattern':'plus','match_type':'ends_with'}))

    def test_company_lookups_are_type_specific(self):
        values = self.funcs['brand_values_by_source'](self.brand, {'dist':'ACME SUPPLY','end':'Final Customer'})
        self.assertEqual(values['distributor-id'], ['Northstar'])
        self.assertEqual(values['end-user-id'], ['NORTHSTAR PLUS'])

    def test_or_across_ticket_distributor_and_end_user(self):
        rule = {'pattern':'north', 'match_type':'contains', 'sources':['ticket', 'distributor-id', 'end-user-id']}
        fn = self.funcs['rule_matches']
        self.assertTrue(fn(self.brand, {'brand':'other','dist':'Acme Supply'}, rule))
        self.assertTrue(fn(self.brand, {'brand':'other','end':'Final Customer'}, rule))
        self.assertTrue(fn(self.brand, {'brand':'Northstar','dist':'Unknown'}, rule))

    def test_wrong_type_and_unknown_company_do_not_match(self):
        rule = {'pattern':'wrong type', 'match_type':'contains', 'sources':['distributor-id']}
        self.assertFalse(self.funcs['rule_matches'](self.brand, {'dist':'Acme Supply'}, rule))
        self.assertFalse(self.funcs['rule_matches'](self.brand, {'dist':'Unknown'}, rule))

    def test_pending_review_prevents_matching(self):
        rule = {'pattern':'northstar', 'match_type':'contains', 'sources':['ticket'], 'pending_brand_review':True}
        self.assertFalse(self.funcs['rule_matches'](self.brand, {'brand':'Northstar'}, rule))

    def test_recipients_are_union_and_deduplicated(self):
        self.brand.brand_cc_rules = [
            {'pattern':'northstar', 'match_type':'contains', 'sources':['distributor-id'], 'cc_emails':['A@example.com', 'b@example.com']},
            {'pattern':'northstar', 'match_type':'contains', 'sources':['ticket'], 'cc_emails':['a@example.com', 'c@example.com']},
        ]
        self.assertEqual(self.funcs['brand_cc_recipients'](self.brand.table, {'dist':'Acme Supply', 'brand':'northstar'}),
                         ['A@example.com', 'b@example.com', 'c@example.com'])


if __name__ == '__main__':
    unittest.main()
