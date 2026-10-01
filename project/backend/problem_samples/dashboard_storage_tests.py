import os
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import ProblemImage, ProblemSample, ProblemTable


class DashboardStorageTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.user = User.objects.create_user(username='storage.dashboard')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        table = ProblemTable.objects.create(name='Storage dashboard table', is_default=True)
        self.problem = ProblemSample.objects.create(table=table, problem_number=1)

    def test_reports_actual_image_bytes_and_missing_records(self):
        first = ProblemImage.objects.create(
            problem=self.problem,
            image=SimpleUploadedFile('one.webp', b'a' * 100, content_type='image/webp'),
            original_name='one.webp',
            uploaded_by=self.user,
        )
        missing = ProblemImage.objects.create(
            problem=self.problem,
            image=SimpleUploadedFile('missing.webp', b'b' * 200, content_type='image/webp'),
            original_name='missing.webp',
            uploaded_by=self.user,
        )
        os.remove(missing.image.path)

        response = self.client.get('/api/dashboard/storage/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['image_file_count'], 1)
        self.assertEqual(response.data['database_image_records'], 2)
        self.assertEqual(response.data['total_image_bytes'], 100)
        self.assertEqual(response.data['average_image_bytes'], 100)
        self.assertEqual(response.data['missing_image_file_count'], 1)
        self.assertEqual(response.data['orphan_image_file_count'], 0)
        self.assertIsNotNone(response.data['volume_free_bytes'])
        self.assertGreaterEqual(response.data['estimated_images_remaining'], 0)
        self.assertTrue(first.image.name.startswith('problem-images/'))

    def test_marks_railway_volume_when_mount_environment_is_present(self):
        with patch.dict(os.environ, {'RAILWAY_VOLUME_MOUNT_PATH': self.media_dir.name}):
            response = self.client.get('/api/dashboard/storage/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['persistent_volume_configured'])
        self.assertEqual(response.data['storage_kind'], 'railway_volume')

    def test_requires_authentication(self):
        response = APIClient().get('/api/dashboard/storage/')
        self.assertIn(response.status_code, (401, 403))
