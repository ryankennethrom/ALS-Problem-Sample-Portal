"""Manual tracker backup/restore helpers.

Backups are application-level archives, intentionally independent of pg_dump so
admins can create/restore them from the running app without requiring a matching
PostgreSQL client binary in the web container.

Durable tracker data is serialized with Django. Authentication/login session
secrets and rate-limit buckets are intentionally excluded. Media bytes are
streamed directly from MEDIA_ROOT into the download archive; a second copy of
all media is never written to the Railway volume.
"""

from __future__ import annotations

import hashlib
import contextlib
import io
import json
import os
import queue
import shutil
import tarfile
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable

import django
from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone


BACKUP_FORMAT = 'edmonton-ticket-tracker-backup'
BACKUP_VERSION = 1
DATABASE_MEMBER = 'database.json'
MANIFEST_MEMBER = 'manifest.json'
MEDIA_PREFIX = 'media/'
DATABASE_SPOOL_MEMORY_BYTES = 16 * 1024 * 1024
MAX_DATABASE_FIXTURE_BYTES = 512 * 1024 * 1024
RESTORE_HEADROOM_BYTES = 16 * 1024 * 1024
BACKUP_LOCK_PATH = Path(tempfile.gettempdir()) / 'edmonton-ticket-tracker-backup-restore.lock'

try:
    import fcntl
except ImportError:  # pragma: no cover - Railway/WSL are Linux
    fcntl = None


@contextlib.contextmanager
def backup_restore_lock(*, exclusive: bool, blocking: bool = True):
    """Cross-process lock preventing restore during a backup stream."""
    if fcntl is None:
        yield
        return
    handle = BACKUP_LOCK_PATH.open('a+b')
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    if not blocking:
        operation |= fcntl.LOCK_NB
    try:
        try:
            fcntl.flock(handle.fileno(), operation)
        except BlockingIOError as exc:
            raise BackupError('Another backup or restore is already running. Try again after it finishes.') from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


# These records are deliberately not durable business data. Restoring a database
# therefore logs everyone out and does not resurrect old magic links, prepared
# drafts, or public rate-limit counters.
TRANSIENT_MODEL_EXCLUDES = (
    'accounts.loginlink',
    'accounts.appsession',
    'problem_samples.preparedproblemsample',
    'problem_samples.publictrackingratebucket',
)

DUMP_LABELS = (
    'auth.user',
    'auth.group',
    'accounts.userprofile',
    'customers',
    'problem_samples',
)


class BackupError(Exception):
    pass


@dataclass(frozen=True)
class MediaEntry:
    path: Path
    relative: str
    size: int
    mtime: int


@dataclass(frozen=True)
class InspectedArchive:
    manifest: dict
    members: dict[str, tarfile.TarInfo]
    media_members: tuple[tarfile.TarInfo, ...]


class _QueueWriter:
    """File-like sink that transfers tar/gzip bytes to a bounded queue."""

    def __init__(self, output_queue: queue.Queue):
        self.output_queue = output_queue
        self.position = 0

    def write(self, data):
        if not data:
            return 0
        chunk = bytes(data)
        self.output_queue.put(chunk)
        self.position += len(chunk)
        return len(chunk)

    def tell(self):
        return self.position

    def flush(self):
        return None


_STREAM_END = object()


def current_schema_migrations() -> list[str]:
    applied = MigrationRecorder(connection).applied_migrations()
    return sorted(f'{app}.{name}' for app, name in applied)


def schema_hash(migrations: Iterable[str] | None = None) -> str:
    values = list(migrations if migrations is not None else current_schema_migrations())
    payload = '\n'.join(sorted(values)).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def scan_media() -> list[MediaEntry]:
    root = Path(settings.MEDIA_ROOT)
    if not root.exists():
        return []
    entries: list[MediaEntry] = []
    for current_root, dirnames, filenames in os.walk(root, followlinks=False):
        # Never follow symlinked directories into locations outside MEDIA_ROOT.
        base = Path(current_root)
        dirnames[:] = [name for name in dirnames if not (base / name).is_symlink()]
        for filename in filenames:
            path = base / filename
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                relative = path.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            # Interrupted restore scratch files are never considered real media.
            if '.restore-tmp-' in filename:
                continue
            entries.append(MediaEntry(path=path, relative=relative, size=int(stat.st_size), mtime=int(stat.st_mtime)))
    entries.sort(key=lambda item: item.relative)
    return entries


def _database_fixture_file():
    """Return a seekable temporary file containing the durable Django fixture."""
    tmp = tempfile.SpooledTemporaryFile(max_size=DATABASE_SPOOL_MEMORY_BYTES, mode='w+b')
    text = io.TextIOWrapper(tmp, encoding='utf-8', write_through=True)
    try:
        with transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            call_command(
                'dumpdata',
                *DUMP_LABELS,
                exclude=list(TRANSIENT_MODEL_EXCLUDES),
                natural_foreign=True,
                natural_primary=True,
                verbosity=0,
                stdout=text,
            )
        text.flush()
        text.detach()
        tmp.seek(0, io.SEEK_END)
        size = tmp.tell()
        if size > MAX_DATABASE_FIXTURE_BYTES:
            tmp.close()
            raise BackupError('The tracker data backup is unexpectedly large and was not generated.')
        tmp.seek(0)
        return tmp, size
    except Exception:
        try:
            if not text.closed:
                text.detach()
        except Exception:
            pass
        tmp.close()
        raise


def build_manifest(kind: str, media_entries: list[MediaEntry] | None = None, database_size: int | None = None) -> dict:
    migrations = current_schema_migrations()
    manifest = {
        'format': BACKUP_FORMAT,
        'version': BACKUP_VERSION,
        'kind': kind,
        'created_at': timezone.now().isoformat(),
        'django_version': django.get_version(),
        'timezone': settings.TIME_ZONE,
        'schema_hash': schema_hash(migrations),
        'schema_migrations': migrations,
    }
    if database_size is not None:
        manifest['database'] = {
            'member': DATABASE_MEMBER,
            'format': 'django-json-fixture',
            'size_bytes': int(database_size),
            'excluded_transient_models': list(TRANSIENT_MODEL_EXCLUDES),
        }
    if media_entries is not None:
        manifest['media'] = {
            'prefix': MEDIA_PREFIX,
            'file_count': len(media_entries),
            'total_bytes': sum(item.size for item in media_entries),
        }
    return manifest


def _tar_add_bytes(tar: tarfile.TarFile, name: str, payload: bytes, mtime: int):
    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    info.mtime = mtime
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(payload))


def _tar_add_fileobj(tar: tarfile.TarFile, name: str, fileobj: BinaryIO, size: int, mtime: int):
    info = tarfile.TarInfo(name=name)
    info.size = int(size)
    info.mtime = int(mtime)
    info.mode = 0o600
    tar.addfile(info, fileobj)


def stream_backup_archive(kind: str):
    # The shared lock stays held for the lifetime of the HTTP stream, keeping a
    # Full Backup internally consistent while a restore is prevented.
    with backup_restore_lock(exclusive=False, blocking=True):
        yield from _stream_backup_archive_unlocked(kind)


def _stream_backup_archive_unlocked(kind: str):
    if kind not in {'database', 'media', 'full'}:
        raise BackupError('Unknown backup type.')

    media_entries = scan_media() if kind in {'media', 'full'} else None
    database_file = None
    database_size = None
    if kind in {'database', 'full'}:
        database_file, database_size = _database_fixture_file()

    manifest = build_manifest(kind, media_entries, database_size)
    timestamp = int(timezone.now().timestamp())
    output: queue.Queue = queue.Queue(maxsize=8)

    def produce():
        writer = _QueueWriter(output)
        try:
            with tarfile.open(fileobj=writer, mode='w|gz', compresslevel=6) as tar:
                manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')
                _tar_add_bytes(tar, MANIFEST_MEMBER, manifest_bytes, timestamp)
                if database_file is not None:
                    database_file.seek(0)
                    _tar_add_fileobj(tar, DATABASE_MEMBER, database_file, database_size or 0, timestamp)
                if media_entries is not None:
                    for item in media_entries:
                        try:
                            source = item.path.open('rb')
                        except OSError as exc:
                            raise BackupError(f'Could not read media file {item.relative}.') from exc
                        with source:
                            _tar_add_fileobj(tar, f'{MEDIA_PREFIX}{item.relative}', source, item.size, item.mtime)
        except BaseException as exc:  # surfaced to the streaming iterator
            output.put(exc)
        finally:
            if database_file is not None:
                database_file.close()
            output.put(_STREAM_END)

    threading.Thread(target=produce, name=f'tracker-{kind}-backup', daemon=True).start()

    while True:
        item = output.get()
        if item is _STREAM_END:
            break
        if isinstance(item, BaseException):
            raise item
        yield item


def backup_filename(kind: str) -> str:
    stamp = timezone.localtime().strftime('%Y-%m-%d-%H%M%S')
    return f'edmonton-ticket-tracker-{kind}-backup-{stamp}.tar.gz'


def _safe_archive_name(name: str) -> bool:
    if not name or '\\' in name:
        return False
    value = PurePosixPath(name)
    return not value.is_absolute() and '..' not in value.parts and value.parts[0] not in {'', '.'}


def inspect_backup_archive(uploaded, expected_kind: str | None = None) -> InspectedArchive:
    try:
        uploaded.seek(0)
        with tarfile.open(fileobj=uploaded, mode='r:gz') as tar:
            members_list = tar.getmembers()
            members: dict[str, tarfile.TarInfo] = {}
            for member in members_list:
                if not _safe_archive_name(member.name):
                    raise BackupError('Backup contains an unsafe file path.')
                if not member.isfile():
                    raise BackupError('Backup contains unsupported archive entries.')
                if member.name in members:
                    raise BackupError('Backup contains duplicate files.')
                members[member.name] = member

            manifest_member = members.get(MANIFEST_MEMBER)
            if not manifest_member or manifest_member.size > 1024 * 1024:
                raise BackupError('Backup manifest is missing or invalid.')
            manifest_file = tar.extractfile(manifest_member)
            if manifest_file is None:
                raise BackupError('Backup manifest could not be read.')
            try:
                manifest = json.loads(manifest_file.read().decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BackupError('Backup manifest is invalid.') from exc
    except (tarfile.TarError, OSError) as exc:
        raise BackupError('Choose a valid tracker .tar.gz backup file.') from exc
    finally:
        try:
            uploaded.seek(0)
        except Exception:
            pass

    if manifest.get('format') != BACKUP_FORMAT or manifest.get('version') != BACKUP_VERSION:
        raise BackupError('This file is not a supported Edmonton Ticket Tracker backup.')
    kind = manifest.get('kind')
    if kind not in {'database', 'media', 'full'}:
        raise BackupError('Backup type is invalid.')
    if expected_kind and kind != expected_kind:
        raise BackupError(f'Choose a {expected_kind} backup file for this restore action.')

    allowed_names = {MANIFEST_MEMBER}
    if kind in {'database', 'full'}:
        db_member = members.get(DATABASE_MEMBER)
        if db_member is None or db_member.size > MAX_DATABASE_FIXTURE_BYTES:
            raise BackupError('Database data is missing or too large.')
        expected_size = int((manifest.get('database') or {}).get('size_bytes') or -1)
        if expected_size != db_member.size:
            raise BackupError('Database backup metadata does not match the archive.')
        allowed_names.add(DATABASE_MEMBER)

    media_members = tuple(
        member for name, member in members.items() if name.startswith(MEDIA_PREFIX)
    )
    if kind in {'media', 'full'}:
        media_info = manifest.get('media') or {}
        expected_count = int(media_info.get('file_count') or 0)
        expected_bytes = int(media_info.get('total_bytes') or 0)
        if expected_count != len(media_members) or expected_bytes != sum(m.size for m in media_members):
            raise BackupError('Media backup metadata does not match the archive.')
        allowed_names.update(member.name for member in media_members)

    unexpected = set(members) - allowed_names
    if unexpected:
        raise BackupError('Backup contains unexpected files.')

    return InspectedArchive(manifest=manifest, members=members, media_members=media_members)


def _require_matching_schema(manifest: dict):
    backup_migrations = manifest.get('schema_migrations')
    if not isinstance(backup_migrations, list) or not all(isinstance(item, str) for item in backup_migrations):
        raise BackupError('Backup does not contain valid schema information.')
    current = current_schema_migrations()
    if sorted(backup_migrations) != current or manifest.get('schema_hash') != schema_hash(current):
        raise BackupError(
            'The backup was created with a different database schema. Deploy the same tracker version used to create the backup before restoring it.'
        )


def _copy_member_to_named_temp(uploaded, member_name: str, suffix: str):
    uploaded.seek(0)
    temp = tempfile.NamedTemporaryFile(mode='w+b', suffix=suffix, delete=False)
    temp_path = temp.name
    try:
        with tarfile.open(fileobj=uploaded, mode='r:gz') as tar:
            member = tar.getmember(member_name)
            source = tar.extractfile(member)
            if source is None:
                raise BackupError(f'{member_name} could not be read from the backup.')
            shutil.copyfileobj(source, temp, length=1024 * 1024)
        temp.flush()
        temp.close()
        return temp_path
    except Exception:
        temp.close()
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    finally:
        uploaded.seek(0)


def restore_database(uploaded, inspected: InspectedArchive):
    _require_matching_schema(inspected.manifest)
    fixture_path = _copy_member_to_named_temp(uploaded, DATABASE_MEMBER, '.json')
    try:
        # On PostgreSQL, TRUNCATE/fixture loading remains within this outer
        # transaction. A failed fixture therefore rolls back to the pre-restore
        # database rather than leaving a half-loaded tracker.
        with transaction.atomic():
            call_command('flush', interactive=False, verbosity=0)
            call_command('loaddata', fixture_path, verbosity=0)
    except Exception as exc:
        raise BackupError(f'Database restore failed: {exc}') from exc
    finally:
        try:
            os.unlink(fixture_path)
        except OSError:
            pass
        # The restored database intentionally has no old AppSession rows.
        connections.close_all()


def _media_relative_from_member(member_name: str) -> str:
    if not member_name.startswith(MEDIA_PREFIX):
        raise BackupError('Invalid media member.')
    relative = member_name[len(MEDIA_PREFIX):]
    if not relative or not _safe_archive_name(relative):
        raise BackupError('Backup contains an unsafe media path.')
    return PurePosixPath(relative).as_posix()


def _media_file_map() -> dict[str, int]:
    return {entry.relative: entry.size for entry in scan_media()}


def _ensure_restore_space(media_members: Iterable[tarfile.TarInfo]):
    root = Path(settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    current = _media_file_map()
    members = list(media_members)
    missing_total = 0
    positive_growth = 0
    largest = 0
    for member in members:
        relative = _media_relative_from_member(member.name)
        largest = max(largest, int(member.size))
        old_size = current.get(relative)
        if old_size is None:
            missing_total += int(member.size)
        elif member.size > old_size:
            positive_growth += int(member.size - old_size)
    required = missing_total + positive_growth + largest + RESTORE_HEADROOM_BYTES
    try:
        free = shutil.disk_usage(root).free
    except OSError:
        return
    if required > free:
        raise BackupError(
            f'Not enough free media storage to restore safely. Need about {required:,} free bytes; {free:,} bytes are available.'
        )


def preflight_media_restore(inspected: InspectedArchive):
    _ensure_restore_space(inspected.media_members)


def restore_media(uploaded, inspected: InspectedArchive, *, replace_extras: bool) -> dict:
    members = inspected.media_members
    _ensure_restore_space(members)
    root = Path(settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    expected: set[str] = set()
    restored_bytes = 0
    restored_files = 0

    uploaded.seek(0)
    try:
        with tarfile.open(fileobj=uploaded, mode='r:gz') as tar:
            for original_member in members:
                member = tar.getmember(original_member.name)
                relative = _media_relative_from_member(member.name)
                expected.add(relative)
                destination = root / Path(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                scratch = destination.with_name(f'{destination.name}.restore-tmp-{uuid.uuid4().hex}')
                source = tar.extractfile(member)
                if source is None:
                    raise BackupError(f'Could not read {relative} from the backup.')
                try:
                    with scratch.open('wb') as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(scratch, destination)
                    try:
                        os.utime(destination, (member.mtime, member.mtime))
                    except OSError:
                        pass
                finally:
                    try:
                        if scratch.exists():
                            scratch.unlink()
                    except OSError:
                        pass
                restored_files += 1
                restored_bytes += int(member.size)
    except (tarfile.TarError, OSError) as exc:
        raise BackupError(f'Media restore failed: {exc}') from exc
    finally:
        uploaded.seek(0)

    removed_files = 0
    if replace_extras:
        for entry in scan_media():
            if entry.relative in expected:
                continue
            try:
                entry.path.unlink()
                removed_files += 1
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise BackupError(f'Backup restored, but an old media file could not be removed: {entry.relative}') from exc
        # Tidy empty directories bottom-up without touching MEDIA_ROOT itself.
        for current_root, dirnames, filenames in os.walk(root, topdown=False):
            path = Path(current_root)
            if path == root:
                continue
            try:
                path.rmdir()
            except OSError:
                pass

    return {
        'restored_files': restored_files,
        'restored_bytes': restored_bytes,
        'removed_extra_files': removed_files,
    }


def backup_status() -> dict:
    media_entries = scan_media()
    migrations = current_schema_migrations()
    return {
        'backup_format_version': BACKUP_VERSION,
        'schema_hash': schema_hash(migrations),
        'migration_count': len(migrations),
        'media_file_count': len(media_entries),
        'media_total_bytes': sum(item.size for item in media_entries),
        'media_root': str(settings.MEDIA_ROOT),
        'persistent_media_volume': bool(os.getenv('RAILWAY_VOLUME_MOUNT_PATH')),
        'database_backup_type': 'Django application data',
        'database_restore_logs_out_users': True,
    }
