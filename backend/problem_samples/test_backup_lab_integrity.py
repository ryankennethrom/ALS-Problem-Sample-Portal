"""Regression checks for lab-complete, restorable JSON backup fixtures.

These are SimpleTestCase tests: they do not require a PostgreSQL test database.
Run: python manage.py test problem_samples.test_backup_lab_integrity
"""

import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .backup_restore import (
    BackupError,
    DUMP_LABELS,
    restore_database,
    validate_lab_references_in_fixture,
)


class BackupLabIntegrityTests(SimpleTestCase):
    @staticmethod
    def fixture(*objects):
        return io.BytesIO(json.dumps(list(objects)).encode('utf-8'))

    def test_backup_dump_includes_labs_before_dependent_records(self):
        self.assertIn('accounts.lab', DUMP_LABELS)
        self.assertLess(DUMP_LABELS.index('accounts.lab'), DUMP_LABELS.index('accounts.userprofile'))
        self.assertLess(DUMP_LABELS.index('accounts.lab'), DUMP_LABELS.index('problem_samples'))

    def test_valid_multilab_fixture_is_accepted(self):
        fixture = self.fixture(
            {'model': 'accounts.lab', 'pk': 1, 'fields': {'code': 'EDM', 'name': 'Edmonton'}},
            {'model': 'accounts.lab', 'pk': 2, 'fields': {'code': 'CGY', 'name': 'Calgary'}},
            {'model': 'accounts.userprofile', 'pk': 10, 'fields': {'lab': 1}},
            {'model': 'problem_samples.problemcontainer', 'pk': 1, 'fields': {'lab': 2}},
        )
        # The actual container model name is detected dynamically from Django
        # when a reference is present in the current model registry.
        self.assertEqual(validate_lab_references_in_fixture(fixture), 2)
        self.assertEqual(fixture.tell(), 0, 'preflight must rewind backup fixture file')

    def test_missing_lab_rows_are_rejected(self):
        fixture = self.fixture(
            {'model': 'accounts.userprofile', 'pk': 10, 'fields': {'lab': 1}}
        )
        with self.assertRaisesRegex(BackupError, 'missing accounts.lab'):
            validate_lab_references_in_fixture(fixture)

    def test_missing_referenced_lab_is_rejected(self):
        fixture = self.fixture(
            {'model': 'accounts.lab', 'pk': 2, 'fields': {'code': 'CGY', 'name': 'Calgary'}},
            {'model': 'accounts.userprofile', 'pk': 10, 'fields': {'lab': 1}},
        )
        with self.assertRaisesRegex(BackupError, 'referencing Lab ID 1'):
            validate_lab_references_in_fixture(fixture)

    def test_null_lab_on_legacy_staff_is_allowed(self):
        fixture = self.fixture(
            {'model': 'accounts.lab', 'pk': 1, 'fields': {'code': 'EDM', 'name': 'Edmonton'}},
            {'model': 'accounts.userprofile', 'pk': 10, 'fields': {'lab': None}},
        )
        self.assertEqual(validate_lab_references_in_fixture(fixture), 1)

    def test_duplicate_lab_primary_keys_are_rejected(self):
        fixture = self.fixture(
            {'model': 'accounts.lab', 'pk': 1, 'fields': {}},
            {'model': 'accounts.lab', 'pk': 1, 'fields': {}},
        )
        with self.assertRaisesRegex(BackupError, 'duplicate lab IDs'):
            validate_lab_references_in_fixture(fixture)

    def test_restore_does_not_flush_incomplete_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'database.json'
            path.write_text(json.dumps([
                {'model': 'accounts.userprofile', 'pk': 10, 'fields': {'lab': 1}}
            ]), encoding='utf-8')
            with (
                patch('problem_samples.backup_restore._require_matching_schema'),
                patch('problem_samples.backup_restore._copy_member_to_named_temp', return_value=str(path)),
                patch('problem_samples.backup_restore.call_command') as commands,
                patch('problem_samples.backup_restore.connections.close_all'),
            ):
                with self.assertRaisesRegex(BackupError, 'missing accounts.lab'):
                    restore_database(None, SimpleNamespace(manifest={}))
                commands.assert_not_called()
