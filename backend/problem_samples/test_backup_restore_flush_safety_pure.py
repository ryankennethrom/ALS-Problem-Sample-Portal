"""Dependency-free regression checks for safe PostgreSQL full restores.

Run with: python -m unittest problem_samples.test_backup_restore_flush_safety_pure
These AST checks still run in environments without Django/PostgreSQL.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).parent


def parse_module(name):
    return ast.parse((ROOT / name).read_text(encoding='utf-8'))


def function(module, name):
    return next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name)


def calls_to(node, name):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name]


def command_call(node, kind):
    return next(n for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == 'call_command' and n.args
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == kind)


class RestoreFlushSafetyTests(unittest.TestCase):
    def test_full_restore_enables_foreign_key_cascade(self):
        node = function(parse_module('backup_restore.py'), 'restore_database')
        flush = command_call(node, 'flush')
        kwargs = {kw.arg: kw.value for kw in flush.keywords}
        self.assertIs(kwargs['allow_cascade'].value, True)
        self.assertIs(kwargs['interactive'].value, False)

    def test_full_restore_is_transactional_with_fixture_load(self):
        node = function(parse_module('backup_restore.py'), 'restore_database')
        blocks = [n for n in ast.walk(node) if isinstance(n, ast.With)
                  and any(isinstance(item.context_expr, ast.Call)
                          and isinstance(item.context_expr.func, ast.Attribute)
                          and item.context_expr.func.attr == 'atomic'
                          for item in n.items)]
        self.assertEqual(len(blocks), 1)
        command_call(blocks[0], 'flush')
        command_call(blocks[0], 'loaddata')

    def test_upgrade_restore_enables_foreign_key_cascade(self):
        tree = parse_module('backup_upgrade.py')
        flush = command_call(tree, 'flush')
        kwargs = {kw.arg: kw.value for kw in flush.keywords}
        self.assertIs(kwargs['allow_cascade'].value, True)

    def test_underlying_db_error_is_reported_concisely(self):
        node = function(parse_module('backup_restore.py'), '_database_error_detail')
        ns = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<test>', 'exec'), ns)
        try:
            raise ValueError('cannot truncate referenced table\nsecret second line')
        except ValueError as inner:
            try:
                raise RuntimeError('generic flush failure') from inner
            except RuntimeError as outer:
                result = ns['_database_error_detail'](outer)
        self.assertIn('cannot truncate referenced table', result)
        self.assertNotIn('secret second line', result)
        self.assertEqual(ns['_database_error_detail'](ValueError('no inner error')), '')

    def test_database_error_detail_has_bounded_length(self):
        node = function(parse_module('backup_restore.py'), '_database_error_detail')
        ns = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<test>', 'exec'), ns)
        try:
            raise ValueError('x' * 5000)
        except ValueError as inner:
            try:
                raise RuntimeError('generic flush failure') from inner
            except RuntimeError as outer:
                result = ns['_database_error_detail'](outer)
        self.assertLess(len(result), 300)


if __name__ == '__main__':
    unittest.main()
