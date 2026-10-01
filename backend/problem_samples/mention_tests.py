from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import ProblemMention, ProblemSample, ProblemTable


@override_settings(FRONTEND_URL='https://tracker.example.test')
class TicketMentionTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username='alex.author', first_name='Alex', last_name='Author', email='alex.author@alsglobal.com'
        )
        self.target = User.objects.create_user(
            username='sam.person@alsglobal.com', first_name='Sam', last_name='Person', email='sam.person@alsglobal.com'
        )
        self.other = User.objects.create_user(
            username='other.user', first_name='Other', last_name='User', email='other.user@alsglobal.com'
        )
        self.lab_two = User.objects.create_user(
            username='lab.two', first_name='Lab', last_name='Two', email='lab.two@alsglobal.com'
        )
        self.no_email = User.objects.create_user(username='no.email', first_name='No', last_name='Email')
        self.inactive = User.objects.create_user(
            username='inactive.user', email='inactive.user@alsglobal.com', is_active=False
        )
        UserProfile.objects.update_or_create(user=self.target, defaults={'role': UserProfile.ROLE_LAB_TECHNICIAN})
        UserProfile.objects.update_or_create(user=self.lab_two, defaults={'role': UserProfile.ROLE_LAB_TECHNICIAN})
        UserProfile.objects.update_or_create(user=self.other, defaults={'role': UserProfile.ROLE_CUSTOMER_SERVICE})
        UserProfile.objects.update_or_create(user=self.no_email, defaults={'role': UserProfile.ROLE_LAB_TECHNICIAN})
        self.table = ProblemTable.objects.create(name='Mention test table')
        self.ticket = ProblemSample.objects.create(table=self.table, problem_number=1)
        self.client = APIClient()
        self.client.force_authenticate(self.author)

    def _prepare(self, body):
        return self.client.post(
            f'/api/problem-samples/{self.ticket.id}/prepare-comment-mentions/',
            {'body': body},
            format='json',
        )

    def _post_confirmed(self, body):
        preview = self._prepare(body)
        self.assertEqual(preview.status_code, 200)
        return self.client.post(
            f'/api/problem-samples/{self.ticket.id}/comments/',
            {'body': body, 'mention_email_confirmation_token': preview.data['confirmation_token']},
            format='json',
        )

    def test_preview_generates_one_email_with_full_message_and_confirmation_required(self):
        body = 'Please review this @sam.person.'
        rejected = self.client.post(
            f'/api/problem-samples/{self.ticket.id}/comments/', {'body': body}, format='json'
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(ProblemMention.objects.count(), 0)

        preview = self._prepare(body)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.data['requires_email'])
        self.assertEqual(len(preview.data['emails']), 1)
        draft = preview.data['emails'][0]
        self.assertEqual(draft['recipients'], ['sam.person@alsglobal.com'])
        self.assertIn(body, draft['body'])
        self.assertIn(f'/problems/{self.ticket.id}#follow-ups', draft['body'])
        self.assertIn('https://tracker.example.test/problems/', draft['direct_url'])

    def test_multiple_individual_mentions_use_one_email_to_every_recipient(self):
        body = 'Please review together @sam.person and @other.user.'
        preview = self._prepare(body)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len(preview.data['emails']), 1)
        draft = preview.data['emails'][0]
        self.assertEqual(
            set(address.lower() for address in draft['recipients']),
            {'sam.person@alsglobal.com', 'other.user@alsglobal.com'},
        )
        self.assertIn(body, draft['body'])
        response = self.client.post(
            f'/api/problem-samples/{self.ticket.id}/comments/',
            {'body': body, 'mention_email_confirmation_token': preview.data['confirmation_token']},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProblemMention.objects.count(), 2)

    def test_lab_group_mentions_every_eligible_lab_user_but_emails_shared_mailbox_once(self):
        body = 'Please review this as a team @Lab.'
        preview = self._prepare(body)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len(preview.data['emails']), 1)
        self.assertEqual(preview.data['emails'][0]['recipients'], ['NA.EDM@alsglobal.com'])
        self.assertIn('@Lab', preview.data['emails'][0]['mentions'])

        response = self.client.post(
            f'/api/problem-samples/{self.ticket.id}/comments/',
            {'body': body, 'mention_email_confirmation_token': preview.data['confirmation_token']},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        mentioned_ids = set(ProblemMention.objects.values_list('mentioned_user_id', flat=True))
        self.assertEqual(mentioned_ids, {self.target.id, self.lab_two.id})
        self.assertTrue(all(
            value == 'NA.EDM@alsglobal.com'
            for value in ProblemMention.objects.values_list('notified_email', flat=True)
        ))
        self.assertNotIn(self.no_email.id, mentioned_ids)

    def test_customer_service_group_sends_one_email_to_all_eligible_customer_service_users(self):
        body = 'Customer service please review @CustomerService.'
        preview = self._prepare(body)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len(preview.data['emails']), 1)
        self.assertEqual(preview.data['emails'][0]['recipients'], ['other.user@alsglobal.com'])
        response = self.client.post(
            f'/api/problem-samples/{self.ticket.id}/comments/',
            {'body': body, 'mention_email_confirmation_token': preview.data['confirmation_token']},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(list(ProblemMention.objects.values_list('mentioned_user_id', flat=True)), [self.other.id])

    def test_group_and_individual_mentions_share_one_deduplicated_email(self):
        body = 'Please review @Lab and @other.user.'
        preview = self._prepare(body)
        self.assertEqual(preview.status_code, 200)
        draft = preview.data['emails'][0]
        self.assertEqual(
            set(address.lower() for address in draft['recipients']),
            {'na.edm@alsglobal.com', 'other.user@alsglobal.com'},
        )
        self.assertEqual(len(draft['recipients']), 2)

    def test_comment_creates_one_mention_after_email_confirmation(self):
        body = 'Please review this @sam.person. Repeating @sam.person should not duplicate it.'
        response = self._post_confirmed(body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProblemMention.objects.count(), 1)
        mention = ProblemMention.objects.get()
        self.assertEqual(mention.mentioned_user, self.target)
        self.assertEqual(mention.mentioned_by, self.author)
        self.assertEqual(mention.problem, self.ticket)
        self.assertEqual(mention.notified_email, 'sam.person@alsglobal.com')
        self.assertIsNotNone(mention.email_confirmed_at)
        self.assertEqual(response.data['mentions'][0]['username'], 'sam.person')

    def test_changed_comment_cannot_reuse_confirmation(self):
        preview = self._prepare('Please review @sam.person')
        response = self.client.post(
            f'/api/problem-samples/{self.ticket.id}/comments/',
            {
                'body': 'Changed text @sam.person',
                'mention_email_confirmation_token': preview.data['confirmation_token'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemMention.objects.count(), 0)

    def test_user_without_email_cannot_be_mentioned_individually(self):
        suggestions = self.client.get('/api/problem-samples/mention-users/?q=no.email')
        self.assertEqual(suggestions.status_code, 200)
        self.assertEqual([item for item in suggestions.data if item.get('kind') == 'user'], [])

        preview = self._prepare('Please check @no.email')
        self.assertEqual(preview.status_code, 400)
        self.assertIn('cannot be mentioned until their ALS email is set', preview.data['detail'])

    def test_unknown_inactive_and_email_like_at_text_do_not_create_mentions(self):
        body = 'Unknown @nobody and inactive @inactive.user and email test@sam.person.'
        preview = self._prepare(body)
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.data['requires_email'])
        response = self.client.post(
            f'/api/problem-samples/{self.ticket.id}/comments/', {'body': body}, format='json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProblemMention.objects.count(), 0)

    def test_mentions_inbox_is_private_and_can_be_marked_read(self):
        comment_response = self._post_confirmed('Can you check this @sam.person?')
        self.assertEqual(comment_response.status_code, 201)
        mention = ProblemMention.objects.get()

        self.client.force_authenticate(self.other)
        other = self.client.get('/api/problem-samples/mentions/')
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data['unread_count'], 0)
        self.assertEqual(other.data['results'], [])

        self.client.force_authenticate(self.target)
        inbox = self.client.get('/api/problem-samples/mentions/')
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(inbox.data['unread_count'], 1)
        self.assertEqual(inbox.data['results'][0]['problem_number'], 1)
        self.assertIsNone(inbox.data['results'][0]['read_at'])

        marked = self.client.post(f'/api/problem-samples/mentions/{mention.id}/read/', {}, format='json')
        self.assertEqual(marked.status_code, 200)
        mention.refresh_from_db()
        self.assertIsNotNone(mention.read_at)
        summary = self.client.get('/api/problem-samples/mentions/?summary=1')
        self.assertEqual(summary.data['unread_count'], 0)

    def test_mention_suggestions_include_groups_and_active_staff_with_email(self):
        response = self.client.get('/api/problem-samples/mention-users/?q=')
        self.assertEqual(response.status_code, 200)
        usernames = [entry['username'] for entry in response.data]
        self.assertIn('Lab', usernames)
        self.assertIn('CustomerService', usernames)
        self.assertIn('sam.person', usernames)

        lab_group = self.client.get('/api/problem-samples/mention-users/?q=lab')
        self.assertEqual(lab_group.status_code, 200)
        self.assertEqual(lab_group.data[0]['username'], 'Lab')

        inactive = self.client.get('/api/problem-samples/mention-users/?q=inactive')
        self.assertEqual(inactive.status_code, 200)
        self.assertEqual([item for item in inactive.data if item.get('kind') == 'user'], [])
