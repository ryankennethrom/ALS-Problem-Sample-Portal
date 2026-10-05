import io
import json
import tarfile
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .backup_restore import BACKUP_FORMAT, BACKUP_VERSION, MANIFEST_MEMBER, current_schema_migrations, schema_hash


class BackupRestoreApiTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)

        self.admin = User.objects.create_user(username='backup.admin', email='backup.admin@alsglobal.com')
        UserProfile.objects.create(user=self.admin, is_admin=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _media_archive(self, files: dict[str, bytes]):
        migrations = current_schema_migrations()
        manifest = {
            'format': BACKUP_FORMAT,
            'version': BACKUP_VERSION,
            'kind': 'media',
            'created_at': '2026-10-05T12:00:00-06:00',
            'schema_hash': schema_hash(migrations),
            'schema_migrations': migrations,
            'media': {
                'prefix': 'media/',
                'file_count': len(files),
                'total_bytes': sum(len(payload) for payload in files.values()),
            },
        }
        result = io.BytesIO()
        with tarfile.open(fileobj=result, mode='w:gz') as tar:
            manifest_bytes = json.dumps(manifest).encode()
            info = tarfile.TarInfo(MANIFEST_MEMBER)
            info.size = len(manifest_bytes)
            tar.addfile(info, io.BytesIO(manifest_bytes))
            for relative, payload in files.items():
                info = tarfile.TarInfo(f'media/{relative}')
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
        return result.getvalue()

    def test_status_requires_tracker_admin(self):
        response = self.client.get('/api/admin/backup-restore/')
        self.assertEqual(response.status_code, 200)

        user = User.objects.create_user(username='not.admin', email='not.admin@alsglobal.com')
        UserProfile.objects.create(user=user, is_admin=False)
        other = APIClient()
        other.force_authenticate(user)
        self.assertEqual(other.get('/api/admin/backup-restore/').status_code, 403)

    def test_media_backup_download_is_streamed_tar_archive(self):
        from pathlib import Path
        path = Path(self.media.name) / 'problem-images' / 'sample.webp'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'image-bytes')

        prepared = self.client.post('/api/admin/backup-restore/prepare-download/', {'kind': 'media'}, format='json')
        self.assertEqual(prepared.status_code, 200)

        download = APIClient().post('/api/admin/backup-restore/download/', {'token': prepared.data['token']})
        self.assertEqual(download.status_code, 200)
        archive = b''.join(download.streaming_content)
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            self.assertIn(MANIFEST_MEMBER, tar.getnames())
            self.assertIn('media/problem-images/sample.webp', tar.getnames())

    def test_media_restore_overwrites_matching_files_and_keeps_extras(self):
        from pathlib import Path
        existing = Path(self.media.name) / 'problem-images' / 'same.webp'
        extra = Path(self.media.name) / 'problem-images' / 'newer.webp'
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b'old')
        extra.write_bytes(b'keep-me')
        archive = self._media_archive({'problem-images/same.webp': b'restored'})

        response = self.client.post('/api/admin/backup-restore/restore/', {
            'kind': 'media',
            'confirmation': 'RESTORE MEDIA',
            'backup': SimpleUploadedFile('media-backup.tar.gz', archive, content_type='application/gzip'),
        }, format='multipart')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(existing.read_bytes(), b'restored')
        self.assertEqual(extra.read_bytes(), b'keep-me')
        self.assertTrue(response.data['merge_restore'])
