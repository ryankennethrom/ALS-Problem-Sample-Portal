"""Mocked Django tests for Full Restore without touching a live database.

Run: python manage.py test problem_samples.test_backup_restore_flush_django
"""
import contextlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .backup_restore import BackupError, restore_database


class RestoreFlushDjangoTests(SimpleTestCase):
    def _restore_with_mocks(self, command_side_effect=None):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'fixture.json'
            fixture.write_text('[]', encoding='utf-8')
            with (
                patch('problem_samples.backup_restore._require_matching_schema'),
                patch('problem_samples.backup_restore._copy_member_to_named_temp', return_value=str(fixture)),
                patch('problem_samples.backup_restore.validate_lab_references_in_fixture'),
                patch('problem_samples.backup_restore.transaction.atomic', return_value=contextlib.nullcontext()),
                patch('problem_samples.backup_restore.connections.close_all'),
                patch('problem_samples.backup_restore.call_command', side_effect=command_side_effect) as commands,
            ):
                restore_database(None, SimpleNamespace(manifest={}))
                return commands.call_args_list

    def test_full_restore_flushes_with_cascade_before_loading(self):
        calls = self._restore_with_mocks()
        self.assertEqual(calls[0].args, ('flush',))
        self.assertTrue(calls[0].kwargs['allow_cascade'])
        self.assertFalse(calls[0].kwargs['interactive'])
        self.assertEqual(calls[1].args[0], 'loaddata')

    def test_postgresql_failure_includes_root_cause(self):
        def fail_flush(*args, **kwargs):
            try:
                raise RuntimeError('cannot truncate table due to dependent key')
            except RuntimeError as original:
                raise RuntimeError('Database could not be flushed') from original
        with self.assertRaisesRegex(BackupError, 'dependent key'):
            self._restore_with_mocks(fail_flush)
