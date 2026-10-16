import base64
import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT,
    DISPOSE_AUTOMATICALLY_NO,
    ProblemAttachment,
    ProblemHistory,
    ProblemImage,
    ProblemSample,
    ProblemTable,
    ProblemTrackingLink,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
    generate_acknowledgement_token,
)


# Tiny valid PNG; backend converts it through the normal WebP compressor.
PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


class CustomerRequestedInfoFileUploadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='tracker-customer-files-')
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.client = APIClient()
        self.table = ProblemTable.objects.create(name='Tickets', is_default=True)
        self.problem = ProblemSample.objects.create(
            table=self.table,
            problem_number=1,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={
                SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY: DISPOSE_AUTOMATICALLY_NO,
            },
        )
        self.link = ProblemTrackingLink.objects.create(
            ticket=self.problem,
            tracking_token=generate_acknowledgement_token(),
        )
        self.url = f'/api/public/problem-sample-tracking/{self.link.tracking_token}/'

    def test_requested_information_can_include_image_and_attachment(self):
        image = SimpleUploadedFile('customer-photo.png', PNG_BYTES, content_type='image/png')
        attachment = SimpleUploadedFile('customer-notes.txt', b'additional customer notes', content_type='text/plain')

        response = self.client.post(
            self.url,
            {
                'action': 'requested_info',
                'signature': 'Customer Name',
                'requested_information': 'Please see the photo and notes attached.',
                'images': [image],
                'attachments': [attachment],
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 200, response.data)
        saved_image = ProblemImage.objects.get(problem=self.problem)
        saved_attachment = ProblemAttachment.objects.get(problem=self.problem)
        self.assertEqual(saved_image.original_name, 'customer-photo.png')
        self.assertTrue(saved_image.image.name.lower().endswith('.webp'))
        self.assertIsNone(saved_image.uploaded_by)
        self.assertEqual(saved_attachment.original_name, 'customer-notes.txt')
        self.assertIsNone(saved_attachment.uploaded_by)

        self.assertEqual(len(response.data['images']), 1)
        self.assertEqual(len(response.data['attachments']), 1)
        history = ProblemHistory.objects.filter(
            problem=self.problem,
            summary='Customer selected: Message us about the issue',
        ).latest('created_at')
        self.assertEqual(history.details['customer_requested_information'], 'Please see the photo and notes attached.')
        self.assertEqual(history.details['customer_uploaded_images'][0]['name'], 'customer-photo.png')
        self.assertEqual(history.details['customer_uploaded_attachments'][0]['name'], 'customer-notes.txt')

    def test_customer_files_are_deleted_from_storage_when_ticket_is_deleted(self):
        response = self.client.post(
            self.url,
            {
                'action': 'requested_info',
                'signature': 'Customer Name',
                'requested_information': 'Files for this ticket.',
                'images': [SimpleUploadedFile('photo.png', PNG_BYTES, content_type='image/png')],
                'attachments': [SimpleUploadedFile('notes.txt', b'notes', content_type='text/plain')],
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)

        image = ProblemImage.objects.get(problem=self.problem)
        attachment = ProblemAttachment.objects.get(problem=self.problem)
        image_path = image.image.path
        attachment_path = attachment.file.path
        self.assertTrue(os.path.exists(image_path))
        self.assertTrue(os.path.exists(attachment_path))

        self.problem.delete()

        self.assertFalse(os.path.exists(image_path))
        self.assertFalse(os.path.exists(attachment_path))
        self.assertFalse(ProblemImage.objects.filter(pk=image.pk).exists())
        self.assertFalse(ProblemAttachment.objects.filter(pk=attachment.pk).exists())

    def test_files_are_rejected_for_non_details_customer_actions(self):
        response = self.client.post(
            self.url,
            {
                'action': 'dispose',
                'signature': 'Customer Name',
                'images': [SimpleUploadedFile('photo.png', PNG_BYTES, content_type='image/png')],
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemImage.objects.filter(problem=self.problem).count(), 0)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.customer_acknowledgement_action, '')

    def test_customer_can_send_camera_photo_without_text_and_staff_can_reply(self):
        """Phone-camera photos should be visible in the chat and auditable history."""
        from .views import _customer_message_history, _customer_history_reply_email
        response = self.client.post(
            self.url,
            {
                'action': 'requested_info',
                'signature': 'Customer Name',
                'requested_information': '',
                'images': [SimpleUploadedFile('phone-photo.jpg', PNG_BYTES, content_type='image/png')],
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProblemImage.objects.filter(problem=self.problem).count(), 1)
        customer_messages = [message for message in response.data['conversation'] if message['sender'] == 'customer']
        self.assertEqual(len(customer_messages), 1)
        self.assertEqual(customer_messages[0]['message'], '')
        self.assertEqual(customer_messages[0]['images'][0]['name'], 'phone-photo.jpg')
        history = ProblemHistory.objects.filter(
            problem=self.problem,
            summary='Customer selected: Message us about the issue',
        ).latest('created_at')
        self.assertIsNotNone(_customer_message_history(self.problem, history.id))
        reply = _customer_history_reply_email(self.problem, history, 'Photo received.', ['example@example.com'])
        self.assertIn('Customer sent 1 photo(s)', reply['body'])

    def test_customer_can_send_attachment_without_text(self):
        response = self.client.post(
            self.url,
            {
                'action': 'requested_info',
                'signature': 'Customer Name',
                'attachments': [SimpleUploadedFile('notes.txt', b'notes', content_type='text/plain')],
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        customer_messages = [message for message in response.data['conversation'] if message['sender'] == 'customer']
        self.assertEqual(len(customer_messages), 1)
        self.assertEqual(customer_messages[0]['message'], '')
        self.assertEqual(customer_messages[0]['attachments'][0]['name'], 'notes.txt')

    def test_empty_customer_message_with_no_files_is_rejected(self):
        response = self.client.post(
            self.url,
            {'action': 'requested_info', 'signature': 'Customer Name', 'requested_information': '  '},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('message or attach', response.data['detail'])
        self.assertFalse(ProblemHistory.objects.filter(problem=self.problem).exists())
