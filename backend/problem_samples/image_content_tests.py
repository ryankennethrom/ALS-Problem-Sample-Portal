import os
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import ProblemImage, ProblemSample, ProblemTable


class StaffImageContentTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.user = User.objects.create_user(username='image.staff')
        self.table = ProblemTable.objects.create(name='Image API table', is_default=True)
        self.problem = ProblemSample.objects.create(table=self.table, problem_number=1)
        self.image = ProblemImage.objects.create(
            problem=self.problem,
            image=SimpleUploadedFile('ticket-photo.png', b'png-bytes', content_type='image/png'),
            original_name='ticket-photo.png',
            uploaded_by=self.user,
        )
        self.url = f'/api/problem-samples/{self.problem.pk}/images/{self.image.pk}/content/'

    def test_authenticated_staff_can_stream_image(self):
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(b''.join(response.streaming_content), b'png-bytes')

    def test_image_content_requires_authentication(self):
        response = APIClient().get(self.url)
        self.assertIn(response.status_code, (401, 403))

    def test_missing_file_returns_404_instead_of_broken_media_url(self):
        os.remove(self.image.image.path)
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'Image file is unavailable.')

class StaffImageMetadataTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.user = User.objects.create_user(username='image.metadata.staff')
        self.table = ProblemTable.objects.create(name='Image metadata table', is_default=True)
        self.problem = ProblemSample.objects.create(table=self.table, problem_number=2)
        self.image = ProblemImage.objects.create(
            problem=self.problem,
            image=SimpleUploadedFile('metadata-photo.jpg', b'jpeg-bytes', content_type='image/jpeg'),
            original_name='metadata-photo.jpg',
            uploaded_by=self.user,
        )

    def test_staff_ticket_payload_does_not_expose_storage_media_url(self):
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(f'/api/problem-samples/{self.problem.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['images']), 1)
        image_data = response.data['images'][0]
        self.assertNotIn('image', image_data)
        self.assertTrue(image_data['has_image'])
        self.assertNotIn('/media/', str(image_data))
        self.assertNotIn('http://', str(image_data))
