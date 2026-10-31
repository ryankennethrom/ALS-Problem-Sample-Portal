import base64
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    CURRENT_WORKFLOW_DEFAULT,
    CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
    ProblemColumn,
    ProblemHistory,
    ProblemImage,
    ProblemAttachment,
    ProblemSample,
    ProblemTable,
    ProblemTrackingLink,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    generate_acknowledgement_token,
)


@override_settings(FRONTEND_URL='https://tracker.example')
class CustomerHistoryReplyTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='tracker-staff-reply-')
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))
        self.user = User.objects.create_user(username='staff.reply', email='staff.reply@alsglobal.com')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = ProblemTable.objects.create(name='Tickets', is_default=True)
        self.email_column = ProblemColumn.objects.create(
            table=self.table,
            name='Client Email',
            field_key='client-email',
            column_type=ProblemColumn.TYPE_CLIENT_EMAIL,
            position=1,
        )
        self.problem = ProblemSample.objects.create(
            table=self.table,
            problem_number=1,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            custom_values={
                SYSTEM_CURRENT_WORKFLOW_FIELD_KEY: CURRENT_WORKFLOW_DEFAULT,
                'client-email': ['customer@example.com', 'second@example.com'],
            },
        )
        self.link = ProblemTrackingLink.objects.create(
            ticket=self.problem,
            tracking_token=generate_acknowledgement_token(),
        )
        self.customer_history = ProblemHistory.objects.create(
            problem=self.problem,
            action=ProblemHistory.ACTION_UPDATED,
            summary='Customer selected: Message us about the issue',
            details={
                'responded_via': 'public_tracking_link',
                'customer_requested_information': 'The bottle arrived damaged.',
                'customer_signature': 'Customer Name',
            },
        )

    def test_prepare_reply_contains_original_message_staff_reply_and_direct_modal_link(self):
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {'history_id': self.customer_history.pk, 'reply': 'Please send us a replacement photo.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        email = response.data['email']
        self.assertEqual(email['to'], ['customer@example.com', 'second@example.com'])
        self.assertIn('The bottle arrived damaged.', email['body'])
        self.assertIn('Please send us a replacement photo.', email['body'])
        self.assertIn('ensure swift correspondence', email['body'])
        self.assertEqual(
            email['direct_url'],
            f'https://tracker.example/track/{self.link.tracking_token}?message=1',
        )
        self.assertIn(email['direct_url'], email['body'])
        self.assertTrue(response.data['confirmation_token'])

    def test_reply_is_not_saved_without_email_confirmation(self):
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {'history_id': self.customer_history.pk, 'reply': 'Staff response'},
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ProblemHistory.objects.filter(problem=self.problem, summary='Replied to customer message').exists())

    def test_confirmed_reply_is_saved_and_moves_cs_follow_up_to_waiting(self):
        reply = 'Please use the link to send another photo.'
        prepared = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {'history_id': self.customer_history.pk, 'reply': reply},
            format='json',
        )
        self.assertEqual(prepared.status_code, 200, prepared.data)
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {
                'history_id': self.customer_history.pk,
                'reply': reply,
                'confirmation_token': prepared.data['confirmation_token'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.workflow_status, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)
        history = ProblemHistory.objects.get(problem=self.problem, summary='Replied to customer message')
        self.assertEqual(history.actor, self.user)
        self.assertEqual(history.details['replied_to_history_id'], self.customer_history.pk)
        self.assertEqual(history.details['customer_message'], 'The bottle arrived damaged.')
        self.assertEqual(history.details['staff_reply'], reply)
        self.assertEqual(history.details['recipients'], ['customer@example.com', 'second@example.com'])
        self.assertEqual(history.details['changes'][0]['field'], 'Current Workflow')

    def test_changed_reply_invalidates_confirmation(self):
        prepared = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {'history_id': self.customer_history.pk, 'reply': 'First reply'},
            format='json',
        )
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {
                'history_id': self.customer_history.pk,
                'reply': 'Changed reply',
                'confirmation_token': prepared.data['confirmation_token'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ProblemHistory.objects.filter(problem=self.problem, summary='Replied to customer message').exists())

    def test_staff_reply_files_are_shown_in_customer_chat_not_emailed(self):
        image_bytes = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
        )
        prepared = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {
                'history_id': self.customer_history.pk,
                'reply': 'Please see the attached photo and instructions.',
                'reply_files': {
                    'images': [{'name': 'reply-photo.png', 'size': len(image_bytes)}],
                    'attachments': [{'name': 'instructions.txt', 'size': len(b'additional details')}],
                },
            }, format='json',
        )
        self.assertEqual(prepared.status_code, 200, prepared.data)
        self.assertIn('[View image/file in the tracking link chat]', prepared.data['email']['body'])
        self.assertNotIn('reply-photo.png', prepared.data['email']['body'])
        self.assertFalse(ProblemImage.objects.filter(problem=self.problem).exists())
        self.assertFalse(ProblemAttachment.objects.filter(problem=self.problem).exists())

        reply = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {
                'history_id': self.customer_history.pk,
                'reply': 'Please see the attached photo and instructions.',
                'confirmation_token': prepared.data['confirmation_token'],
                'images': [SimpleUploadedFile('reply-photo.png', image_bytes, content_type='image/png')],
                'attachments': [SimpleUploadedFile('instructions.txt', b'additional details', content_type='text/plain')],
            }, format='multipart',
        )
        self.assertEqual(reply.status_code, 201, reply.data)
        saved_image = ProblemImage.objects.get(problem=self.problem)
        saved_attachment = ProblemAttachment.objects.get(problem=self.problem)
        self.assertEqual(saved_image.uploaded_by, self.user)
        self.assertEqual(saved_attachment.uploaded_by, self.user)
        history = ProblemHistory.objects.get(problem=self.problem, summary='Replied to customer message')
        self.assertEqual(history.details['staff_reply_images'][0]['id'], saved_image.pk)
        self.assertEqual(history.details['staff_reply_attachments'][0]['id'], saved_attachment.pk)
        public_client = APIClient()
        public = public_client.get(f'/api/public/problem-sample-tracking/{self.link.tracking_token}/')
        self.assertEqual(public.status_code, 200, public.data)
        staff_message = next(item for item in public.data['conversation'] if item['id'] == history.pk)
        self.assertEqual(staff_message['sender'], 'staff')
        self.assertEqual(staff_message['images'][0]['id'], saved_image.pk)
        self.assertEqual(staff_message['attachments'][0]['id'], saved_attachment.pk)
        self.assertEqual(
            public_client.get(f'/api/public/problem-sample-tracking/{self.link.tracking_token}/images/{saved_image.pk}/').status_code,
            200,
        )
        self.assertEqual(
            public_client.get(f'/api/public/problem-sample-tracking/{self.link.tracking_token}/attachments/{saved_attachment.pk}/').status_code,
            200,
        )

    def test_reply_rejects_changed_attachment_selection(self):
        prepared = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {
                'history_id': self.customer_history.pk, 'reply': 'File attached',
                'reply_files': {'images': [], 'attachments': [{'name': 'original.txt', 'size': 5}]},
            }, format='json',
        )
        self.assertEqual(prepared.status_code, 200, prepared.data)
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {
                'history_id': self.customer_history.pk, 'reply': 'File attached',
                'confirmation_token': prepared.data['confirmation_token'],
                'attachments': [SimpleUploadedFile('changed.txt', b'hello', content_type='text/plain')],
            }, format='multipart',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ProblemAttachment.objects.filter(problem=self.problem).exists())
        self.assertFalse(ProblemHistory.objects.filter(problem=self.problem, summary='Replied to customer message').exists())

    def test_reply_cannot_save_attachments_without_confirmation(self):
        response = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/customer-history-reply-sent/',
            {
                'history_id': self.customer_history.pk, 'reply': 'File attached',
                'attachments': [SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain')],
            }, format='multipart',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ProblemAttachment.objects.filter(problem=self.problem).exists())

    def test_file_free_reply_has_no_attachment_reference(self):
        prepared = self.client.post(
            f'/api/problem-samples/{self.problem.pk}/prepare-customer-history-reply/',
            {'history_id': self.customer_history.pk, 'reply': 'A normal reply'}, format='json',
        )
        self.assertEqual(prepared.status_code, 200, prepared.data)
        self.assertNotIn('[View image/file in the tracking link chat]', prepared.data['email']['body'])
