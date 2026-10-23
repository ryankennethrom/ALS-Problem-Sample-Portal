"""INTERNAL ONLY: stage an old backup in an isolated PostgreSQL database.

Always invoked by backup_upgrade with ALS_UPGRADE_STAGING_DATABASE set.  This
command never runs against a database with a name outside our private prefix.
"""
import contextlib
import json
import os
import traceback
from pathlib import Path

from django.apps import apps as live_apps
from django.core.serializers.base import DeserializationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.management.sql import emit_post_migrate_signal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from problem_samples.backup_restore import DUMP_LABELS, TRANSIENT_MODEL_EXCLUDES
from problem_samples.backup_upgrade import STAGING_ENV_NAME, _database_sql_name, _schema_sql_name


@contextlib.contextmanager
def historical_fixture_model_lookup(historical_apps):
    """Use migration-state models only while deserializing the old fixture.

    Django 5.2/6.0 resolves fixture model labels through
    python.Deserializer._get_model_from_node(), not the removed/nonexistent
    module-level python._get_model. This hook is confined to the isolated
    upgrade subprocess and always restored even if loaddata fails.
    """
    from django.core.serializers import python as python_serializer

    deserializer = python_serializer.Deserializer
    original = vars(deserializer).get('_get_model_from_node')
    if not isinstance(original, staticmethod):
        raise RuntimeError('Unsupported Django fixture deserializer interface.')

    def resolve_historical_model(label):
        try:
            return historical_apps.get_model(label)
        except (LookupError, TypeError, ValueError) as exc:
            raise DeserializationError(f'Invalid historical model identifier: {label}') from exc

    deserializer._get_model_from_node = staticmethod(resolve_historical_model)
    try:
        yield
    finally:
        deserializer._get_model_from_node = original


def _safe_upgrade_failure(phase, exc):
    """Expose an error phase and source location, never fixture or DB values."""
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        frame = frames[-1]
        location = f'{Path(frame.filename).name}:{frame.lineno}'
    else:
        location = 'unknown'
    return f'{phase}: {type(exc).__name__} at {location}'


class Command(BaseCommand):
    help = 'Internal staged conversion of historical backup data (never use against production).'

    def add_arguments(self, parser):
        parser.add_argument('--fixture', required=True)
        parser.add_argument('--manifest', required=True)
        parser.add_argument('--output', required=True)

    def handle(self, *args, **opts):
        db_name = os.environ.get(STAGING_ENV_NAME, '')
        schema_name = os.environ.get('ALS_UPGRADE_STAGING_SCHEMA', '')
        # Fail closed: the worker MUST be confined to a newly created staging
        # database OR a random schema with no search_path fallback to public.
        if bool(db_name) == bool(schema_name):
            raise CommandError('Exactly one isolated staging target is required.')
        if db_name:
            _database_sql_name(db_name)
            if connection.settings_dict['NAME'] != db_name:
                raise CommandError('The worker database is not isolated. Refusing to run.')
        else:
            _schema_sql_name(schema_name)
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_schema(), current_schemas(false)')
                current_schema, search_path = cursor.fetchone()
            if current_schema != schema_name or list(search_path) != [schema_name]:
                raise CommandError('The worker search_path is not restricted to its private schema.')
        phase = 'read backup manifest'
        try:
            manifest = json.loads(Path(opts['manifest']).read_text(encoding='utf-8'))
            old_keys = {tuple(item.split('.', 1)) for item in manifest['schema_migrations']}
            phase = 'reconstruct historical migrations'
            executor = MigrationExecutor(connection)
            graph = executor.loader.graph
            if not old_keys or not old_keys.issubset(set(graph.nodes)):
                raise CommandError('Unsupported historical migration state.')
            # Only migrate to the old schema, including all dependent applications.
            old_targets = sorted(key for key in old_keys if not any(
                key in graph.forwards_plan(other)[:-1] for other in old_keys if other != key
            ))
            executor.migrate(old_targets)
            applied = set(MigrationRecorder(connection).applied_migrations())
            if applied != old_keys:
                raise CommandError('Could not exactly reconstruct the old database schema.')
            # Foreign key fixtures may use content-type and permission natural
            # keys. Populate those in the staging DB before loading the backup.
            phase = 'initialize historical content types'
            old_apps = executor.loader.project_state(old_targets).apps
            emit_post_migrate_signal(verbosity=0, interactive=False, db='default', apps=old_apps)

            # Only in this isolated subprocess, deserialize old fixture records
            # against the historical models instead of today's schema.
            phase = 'load historical JSON fixture'
            with historical_fixture_model_lookup(old_apps):
                call_command('loaddata', opts['fixture'], verbosity=0)

            preserved_models = [
                ('auth', 'User'), ('accounts', 'UserProfile'),
                ('customers', 'Customer'), ('customers', 'CustomerImport'),
                ('problem_samples', 'ProblemSample'), ('problem_samples', 'ProblemTable'),
                ('problem_samples', 'ProblemColumn'), ('problem_samples', 'ProblemContainer'),
                ('problem_samples', 'ProblemHistory'),
            ]
            def snapshot_counts(registry):
                result = {}
                for label in preserved_models:
                    try:
                        result[label] = registry.get_model(*label).objects.count()
                    except LookupError:
                        # A model may only have been introduced after the
                        # historical backup was created.
                        continue
                return result
            phase = 'snapshot historical row counts'
            old_counts = snapshot_counts(old_apps)
            # Applying the modern migration graph to restored historical records
            # executes data migrations against this staging DB, NOT production.
            phase = 'apply modern migrations to isolated data'
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            emit_post_migrate_signal(verbosity=0, interactive=False, db='default')
            phase = 'validate upgraded row counts'
            new_counts = snapshot_counts(live_apps)
            if any(new_counts[label] != count for label, count in old_counts.items()):
                raise CommandError('Core business record counts changed during upgrade; refusing to continue.')
            phase = 'export upgraded JSON fixture'
            with Path(opts['output']).open('w', encoding='utf-8') as output:
                call_command('dumpdata', *DUMP_LABELS, exclude=list(TRANSIENT_MODEL_EXCLUDES),
                             natural_foreign=True, natural_primary=True, verbosity=0, stdout=output)
            self.stdout.write('Staged backup migrated successfully.')
        except Exception as exc:
            # Parent shows a safe summary, never an untrusted traceback.
            self.stderr.write('UPGRADE_ERROR: ' + _safe_upgrade_failure(phase, exc))
            raise CommandError('Staging failed; the active database has not been touched.') from exc
