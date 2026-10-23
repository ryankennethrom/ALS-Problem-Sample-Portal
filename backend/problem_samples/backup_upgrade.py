"""Conservative upgrade path for older Django-JSON tracker backups.

An older backup is NEVER loaded into the active schema.  A private PostgreSQL
DATABASE (not the production schema) is migrated to the backup's state, loaded,
then advanced to the deployed migration state.  Only the resulting current-state
fixture is subsequently loaded into the active database inside a transaction.

This operation requires PostgreSQL CREATEDB on the application's DB role, and
must run during a maintenance window without concurrent application writes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from django.db import DatabaseError
from pathlib import Path

from django.db import connection, transaction
from django.db.migrations.loader import MigrationLoader

from .backup_restore import (
    BackupError, InspectedArchive, _copy_member_to_named_temp,
    _require_matching_schema, current_schema_migrations, preflight_media_restore,
    restore_media, schema_hash, DATABASE_MEMBER, MAX_DATABASE_FIXTURE_BYTES,
)

STAGING_ENV_NAME = 'ALS_UPGRADE_STAGING_DATABASE'
STAGE_PREFIX = 'als_tracker_restore_'
STAGE_SCHEMA_PREFIX = 'als_tracker_upgrade_'
STAGE_TIMEOUT = 15 * 60


def upgrade_plan(manifest: dict, *, require_older: bool = True) -> dict:
    """Reject unknown, diverged, incomplete or tampered migration histories."""
    if connection.vendor != 'postgresql':
        raise BackupError('Restore and Upgrade requires PostgreSQL.')
    backup = manifest.get('schema_migrations')
    if not isinstance(backup, list) or not backup or not all(isinstance(m, str) for m in backup):
        raise BackupError('The backup does not contain a usable migration history.')
    if len(set(backup)) != len(backup) or manifest.get('schema_hash') != schema_hash(backup):
        raise BackupError('The backup migration history is invalid or its checksum does not match.')
    current = set(current_schema_migrations())
    older = set(backup)
    loader = MigrationLoader(connection)
    known = {f'{app}.{name}' for app, name in loader.graph.nodes}
    unknown = sorted(older - known)
    if unknown:
        raise BackupError('The backup requires migrations not included in this deployment: ' + ', '.join(unknown[:8]))
    if not older.issubset(current):
        raise BackupError('The backup is not an ancestor of the running database; downgrades and divergent histories are not supported.')
    if require_older and older == current:
        raise BackupError('The schema already matches. Use the regular Full Restore option.')
    for label in older:
        app, migration = label.split('.', 1)
        for parent in loader.graph.forwards_plan((app, migration)):
            parent_label = f'{parent[0]}.{parent[1]}'
            if parent_label not in older:
                raise BackupError('The backup migration history omits a required dependency: ' + parent_label)
    # Refuse to upgrade while deployed code has unapplied migrations.
    latest = {f'{app}.{name}' for app, name in loader.graph.nodes}
    if current != latest:
        raise BackupError('First run python manage.py migrate on the current application.')
    missing = sorted(current - older)
    return {'missing_migrations': missing, 'missing_count': len(missing),
            'backup_migration_count': len(backup), 'current_migration_count': len(current)}


def can_create_staging_database() -> bool:
    with connection.cursor() as cursor:
        cursor.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = CURRENT_USER')
        row = cursor.fetchone()
    return bool(row and row[0])


def can_create_staging_schema() -> bool:
    # Database-level CREATE suffices for creating a new private schema. Unlike
    # CREATEDB, this is commonly available to the owner of a managed database.
    with connection.cursor() as cursor:
        cursor.execute("SELECT has_database_privilege(current_user, current_database(), 'CREATE')")
        row = cursor.fetchone()
    return bool(row and row[0])


def staging_isolation_mode() -> str:
    if can_create_staging_database():
        return 'database'
    if can_create_staging_schema():
        return 'schema'
    return 'unavailable'


def _schema_sql_name(name: str) -> str:
    if not re.fullmatch(r'als_tracker_upgrade_[0-9a-f]{24}', name):
        raise BackupError('Invalid temporary schema name.')
    return connection.ops.quote_name(name)


def _database_sql_name(name: str) -> str:
    if not re.fullmatch(r'als_tracker_restore_[0-9a-f]{24}', name):
        raise BackupError('Invalid temporary database name.')
    return connection.ops.quote_name(name)


def _make_staging_database() -> str:
    if not can_create_staging_database():
        raise BackupError(
            'This PostgreSQL role cannot create an isolated staging database (CREATEDB required). '
            'No live data was changed. Ask IT to provide a safe staging database or run the upgrade on '
            'a PostgreSQL instance where the app role can create temporary databases.'
        )
    name = STAGE_PREFIX + uuid.uuid4().hex[:24]
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE {_database_sql_name(name)}')
    except DatabaseError as exc:
        raise BackupError('Could not create the isolated staging PostgreSQL database. No live data was changed.') from exc
    return name


def _make_staging_schema() -> str:
    if not can_create_staging_schema():
        raise BackupError('PostgreSQL does not allow this role to create an isolated schema.')
    name = STAGE_SCHEMA_PREFIX + uuid.uuid4().hex[:24]
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA {_schema_sql_name(name)}')
    except DatabaseError as exc:
        raise BackupError('Could not create an isolated staging schema. No live data was changed.') from exc
    return name


def _remove_staging_schema(name: str):
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS {_schema_sql_name(name)} CASCADE')


def _remove_staging_database(name: str):
    with connection.cursor() as cursor:
        cursor.execute(f'DROP DATABASE IF EXISTS {_database_sql_name(name)}')


def upgrade_full_backup(uploaded, inspected: InspectedArchive) -> dict:
    """Upgrade in a disposable database, then atomically replace live fixture.

    Media is still restored using the existing media routine, which is NOT
    transactional; operations staff should retain their pre-restore full backup.
    """
    if inspected.manifest.get('kind') != 'full':
        raise BackupError('Restore and Upgrade requires a Full Backup.')
    plan = upgrade_plan(inspected.manifest)
    preflight_media_restore(inspected)
    if staging_isolation_mode() == 'unavailable':
        raise BackupError('Cannot safely upgrade: permission to create an isolated PostgreSQL database or schema is required. No live data was changed.')
    fixture_path = _copy_member_to_named_temp(uploaded, DATABASE_MEMBER, '.json')
    stage_db = None
    stage_schema = None
    try:
        with tempfile.TemporaryDirectory(prefix='als-backup-upgrade-') as working:
            manifest_path = Path(working) / 'manifest.json'
            upgraded_fixture = Path(working) / 'upgraded.json'
            manifest_path.write_text(json.dumps(inspected.manifest), encoding='utf-8')
            mode = staging_isolation_mode()
            if mode == 'database':
                stage_db = _make_staging_database()
            elif mode == 'schema':
                stage_schema = _make_staging_schema()
            else:
                raise BackupError('No safe isolated staging environment is available.')
            env = os.environ.copy()
            env.pop(STAGING_ENV_NAME, None)
            env.pop('ALS_UPGRADE_STAGING_SCHEMA', None)
            if stage_db:
                env[STAGING_ENV_NAME] = stage_db
            if stage_schema:
                env['ALS_UPGRADE_STAGING_SCHEMA'] = stage_schema
            env['ALS_UPGRADE_STAGE_MEDIA_ROOT'] = str(Path(working) / 'staging-media')
            backend = Path(__file__).resolve().parent.parent
            command = [sys.executable, str(backend / 'manage.py'), 'stage_backup_upgrade',
                       '--fixture', fixture_path, '--manifest', str(manifest_path),
                       '--output', str(upgraded_fixture)]
            try:
                proc = subprocess.run(command, cwd=str(backend), env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      timeout=STAGE_TIMEOUT, text=True, check=False)
            except subprocess.TimeoutExpired as exc:
                raise BackupError('The isolated backup upgrade timed out. No live data was changed.') from exc
            if proc.returncode != 0:
                # No raw subprocess traceback: it may reveal sensitive database details.
                tail = (proc.stderr or proc.stdout or '').strip().splitlines()
                safe = next((line.removeprefix('UPGRADE_ERROR: ').strip() for line in tail
                             if line.startswith('UPGRADE_ERROR: ')), None)
                raise BackupError('Isolated backup upgrade failed. No live data was changed. '
                                  + (safe or 'Check the backend logs for the staging-migration error.'))
            if not upgraded_fixture.is_file() or not 0 < upgraded_fixture.stat().st_size <= MAX_DATABASE_FIXTURE_BYTES:
                raise BackupError('Staged upgraded data is missing or too large. No live data was changed.')
            # Live data changes ONLY after the historical fixture and all newer
            # migrations have succeeded on an isolated PostgreSQL database.
            from django.core.management import call_command
            from django.db import connections
            try:
                with transaction.atomic():
                    call_command('flush', interactive=False, verbosity=0)
                    call_command('loaddata', str(upgraded_fixture), verbosity=0)
            except Exception as exc:
                raise BackupError('The live database rejected the upgraded fixture; '
                                  'database changes were rolled back. Check server logs.') from exc
            finally:
                connections.close_all()
            # Database now points at the archived media references. Keep the
            # current media procedure's disk-space preflight, but note that file
            # writes/deletes are not protected by a PostgreSQL transaction.
            media_result = restore_media(uploaded, inspected, replace_extras=True)
            return {**plan, 'database_restored': True, 'media_restored': True,
                    'requires_relogin': True, 'upgraded_backup': True, **media_result}
    finally:
        try:
            os.unlink(fixture_path)
        except FileNotFoundError:
            pass
        if stage_db or stage_schema:
            try:
                if stage_db:
                    _remove_staging_database(stage_db)
                else:
                    _remove_staging_schema(stage_schema)
            except Exception as exc:
                location = stage_db or stage_schema
                raise BackupError('The restore ended, but an isolated staging area could not be removed: '
                                  + location + '. Ask the database administrator to remove it.') from exc
