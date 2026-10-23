"""Safeguards for old Full Backup upgrade compatibility checks.

Integration tests must additionally be run with a PostgreSQL testing role that
can create isolated schemas; the build environment lacks Django/PostgreSQL.
"""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .backup_restore import BackupError, schema_hash
from .backup_upgrade import upgrade_plan


class UpgradePlanSafetyTests(SimpleTestCase):
    def setUp(self):
        self.migrations = ['accounts.0001_initial', 'problem_samples.0001_initial',
                           'problem_samples.0002_add_field']
        self.graph = Mock()
        self.graph.nodes = {
            ('accounts', '0001_initial'), ('problem_samples', '0001_initial'),
            ('problem_samples', '0002_add_field'),
        }
        dependency_map = {
            ('accounts', '0001_initial'): [('accounts', '0001_initial')],
            ('problem_samples', '0001_initial'): [('accounts', '0001_initial'), ('problem_samples', '0001_initial')],
            ('problem_samples', '0002_add_field'): [('accounts', '0001_initial'),
                                                 ('problem_samples', '0001_initial'),
                                                 ('problem_samples', '0002_add_field')],
        }
        self.graph.forwards_plan.side_effect = lambda node: dependency_map[node]
        self.loader = patch('problem_samples.backup_upgrade.MigrationLoader').start()
        self.loader.return_value.graph = self.graph
        self.addCleanup(patch.stopall)
        patch('problem_samples.backup_upgrade.current_schema_migrations', return_value=self.migrations).start()
        patch('problem_samples.backup_upgrade.connection', Mock(vendor='postgresql')).start()

    def manifest(self, migrations):
        return {'schema_migrations': migrations, 'schema_hash': schema_hash(migrations)}

    def test_old_backup_with_complete_ancestry_is_supported(self):
        report = upgrade_plan(self.manifest(self.migrations[:2]))
        self.assertEqual(report['missing_migrations'], ['problem_samples.0002_add_field'])

    def test_matching_backup_should_use_regular_restore(self):
        with self.assertRaisesMessage(BackupError, 'already matches'):
            upgrade_plan(self.manifest(self.migrations))

    def test_non_ancestor_is_rejected(self):
        backup = self.manifest(['accounts.0001_initial', 'problem_samples.0999_future'])
        with self.assertRaises(BackupError):
            upgrade_plan(backup)

    def test_missing_dependency_is_rejected(self):
        with self.assertRaisesMessage(BackupError, 'omits a required dependency'):
            upgrade_plan(self.manifest(['problem_samples.0001_initial']))

    def test_tampered_hash_is_rejected(self):
        backup = self.manifest(self.migrations[:2])
        backup['schema_hash'] = 'bad'
        with self.assertRaisesMessage(BackupError, 'checksum'):
            upgrade_plan(backup)


class UpgradeIsolationTests(SimpleTestCase):
    def test_generated_staging_names_are_constrained(self):
        from .backup_upgrade import _database_sql_name, _schema_sql_name
        with patch('problem_samples.backup_upgrade.connection', Mock(ops=Mock(quote_name=lambda value: f'"{value}"'))):
            with self.assertRaises(BackupError):
                _database_sql_name('public')
            with self.assertRaises(BackupError):
                _schema_sql_name('public')
            with self.assertRaises(BackupError):
                _schema_sql_name('als_tracker_upgrade_123;DROP SCHEMA public')
            self.assertEqual(_schema_sql_name('als_tracker_upgrade_' + 'a' * 24),
                             '"als_tracker_upgrade_' + 'a' * 24 + '"')

    def test_failed_staging_process_never_invokes_live_restore(self):
        import io
        import tempfile
        from pathlib import Path
        from unittest.mock import MagicMock
        from .backup_upgrade import upgrade_full_backup
        mock_archive = Mock()
        mock_archive.manifest = {'kind': 'full'}
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as original:
            original.write(b'[]')
            path = original.name
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        with patch('problem_samples.backup_upgrade.upgrade_plan', return_value={'missing_count': 1}), \
             patch('problem_samples.backup_upgrade.preflight_media_restore'), \
             patch('problem_samples.backup_upgrade.staging_isolation_mode', return_value='database'), \
             patch('problem_samples.backup_upgrade._copy_member_to_named_temp', return_value=path), \
             patch('problem_samples.backup_upgrade._make_staging_database', return_value='als_tracker_restore_' + 'a' * 24), \
             patch('problem_samples.backup_upgrade._remove_staging_database') as cleanup, \
             patch('problem_samples.backup_upgrade.subprocess.run', return_value=Mock(returncode=1, stderr='staging error', stdout='')), \
             patch('django.core.management.call_command') as live_command:
            with self.assertRaisesMessage(BackupError, 'No live data was changed'):
                upgrade_full_backup(io.BytesIO(b''), mock_archive)
            live_command.assert_not_called()
            cleanup.assert_called_once()


class HistoricalFixtureCompatibilityTests(SimpleTestCase):
    """Prevent regressions from patching removed Django serializer internals."""

    def test_historical_lookup_is_used_and_restored_after_success(self):
        from django.core.serializers import python as python_serializer
        from .management.commands.stage_backup_upgrade import historical_fixture_model_lookup

        deserializer = python_serializer.Deserializer
        original = vars(deserializer)['_get_model_from_node']
        historical = Mock()
        historical.get_model.return_value = object()
        with historical_fixture_model_lookup(historical):
            self.assertIs(deserializer._get_model_from_node('problem_samples.problemsample'),
                          historical.get_model.return_value)
            historical.get_model.assert_called_once_with('problem_samples.problemsample')
        self.assertIs(vars(deserializer)['_get_model_from_node'], original)

    def test_historical_lookup_is_restored_after_failure(self):
        from django.core.serializers import python as python_serializer
        from .management.commands.stage_backup_upgrade import historical_fixture_model_lookup

        deserializer = python_serializer.Deserializer
        original = vars(deserializer)['_get_model_from_node']
        with self.assertRaisesMessage(RuntimeError, 'fixture failure'):
            with historical_fixture_model_lookup(Mock()):
                raise RuntimeError('fixture failure')
        self.assertIs(vars(deserializer)['_get_model_from_node'], original)

    def test_historical_lookup_rejects_unknown_models(self):
        from django.core.serializers import python as python_serializer
        from django.core.serializers.base import DeserializationError
        from .management.commands.stage_backup_upgrade import historical_fixture_model_lookup

        historical = Mock()
        historical.get_model.side_effect = LookupError('missing')
        with historical_fixture_model_lookup(historical):
            with self.assertRaises(DeserializationError):
                python_serializer.Deserializer._get_model_from_node('invalid.model')

    def test_worker_error_reports_stage_and_location_without_sensitive_values(self):
        from .management.commands.stage_backup_upgrade import _safe_upgrade_failure
        try:
            raise AttributeError('secret connection string')
        except AttributeError as exc:
            message = _safe_upgrade_failure('load historical JSON fixture', exc)
        self.assertIn('load historical JSON fixture: AttributeError', message)
        self.assertIn('test_backup_upgrade.py:', message)
        self.assertNotIn('secret connection string', message)


class HistoricalNaturalKeyUpgradeTests(SimpleTestCase):
    """The staged worker must normalize username-based FKs before loaddata."""

    def test_safe_error_summary_shows_chained_exception_types_not_values(self):
        from .management.commands.stage_backup_upgrade import _safe_upgrade_failure
        try:
            try:
                raise AttributeError('sensitive customer content')
            except AttributeError as root:
                raise ValueError('other sensitive content') from root
        except ValueError as exc:
            msg = _safe_upgrade_failure('load historical JSON fixture', exc)
        self.assertIn('ValueError', msg)
        self.assertIn('AttributeError', msg)
        self.assertNotIn('sensitive customer content', msg)
        self.assertNotIn('other sensitive content', msg)
