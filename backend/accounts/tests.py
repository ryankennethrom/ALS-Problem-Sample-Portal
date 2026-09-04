from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import UserProfile


class AdminCreatedAccountTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin.user',
            password='AdminPassword123!',
            first_name='Admin',
            last_name='User',
        )
        UserProfile.objects.create(user=self.admin, is_admin=True)

    def _login(self, username, password):
        response = self.client.post('/api/auth/login/', {
            'username': username,
            'password': password,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_admin_can_create_named_account_and_generated_password_logs_in(self):
        admin_login = self._login('admin.user', 'AdminPassword123!')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_login['token']}")

        response = self.client.post('/api/auth/accounts/', {
            'first_name': 'Jane',
            'last_name': 'Smith',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['username'], 'jane.smith')
        self.assertTrue(response.data['generated_password'])

        generated_password = response.data['generated_password']
        created = User.objects.get(username='jane.smith')
        self.assertEqual(created.first_name, 'Jane')
        self.assertEqual(created.last_name, 'Smith')
        self.assertEqual(created.email, '')
        self.assertTrue(created.check_password(generated_password))
        self.assertFalse(created.tracker_profile.is_admin)

        self.client.credentials()
        user_login = self._login('jane.smith', generated_password)
        self.assertTrue(user_login['user']['needs_role'])
        self.assertFalse(user_login['user']['is_admin'])

    def test_duplicate_name_gets_numeric_suffix(self):
        User.objects.create_user(username='jane.smith', password='unused')
        admin_login = self._login('admin.user', 'AdminPassword123!')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_login['token']}")
        response = self.client.post('/api/auth/accounts/', {
            'first_name': 'Jane',
            'last_name': 'Smith',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['username'], 'jane.smith2')

    def test_regular_user_cannot_create_accounts(self):
        user = User.objects.create_user(username='regular.user', password='UserPassword123!')
        UserProfile.objects.create(user=user, role=UserProfile.ROLE_LAB_TECHNICIAN)
        user_login = self._login('regular.user', 'UserPassword123!')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_login['token']}")
        response = self.client.post('/api/auth/accounts/', {
            'first_name': 'Blocked',
            'last_name': 'Person',
        }, format='json')
        self.assertEqual(response.status_code, 403)


class AdminAccountManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin.user',
            password='AdminPassword123!',
            first_name='Admin',
            last_name='User',
        )
        UserProfile.objects.create(user=self.admin, is_admin=True)
        self.user = User.objects.create_user(
            username='jane.smith',
            password='UserPassword123!',
            first_name='Jane',
            last_name='Smith',
        )
        UserProfile.objects.create(user=self.user, role=UserProfile.ROLE_LAB_TECHNICIAN)

    def _login(self, username, password):
        response = self.client.post('/api/auth/login/', {
            'username': username,
            'password': password,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def _authenticate_admin(self):
        login = self._login('admin.user', 'AdminPassword123!')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['token']}")
        return login

    def test_admin_can_promote_and_demote_another_user(self):
        self._authenticate_admin()

        promoted = self.client.patch(
            f'/api/auth/accounts/{self.user.id}/admin/',
            {'is_admin': True},
            format='json',
        )
        self.assertEqual(promoted.status_code, 200, promoted.data)
        self.assertTrue(promoted.data['is_admin'])
        self.user.tracker_profile.refresh_from_db()
        self.assertTrue(self.user.tracker_profile.is_admin)

        demoted = self.client.patch(
            f'/api/auth/accounts/{self.user.id}/admin/',
            {'is_admin': False},
            format='json',
        )
        self.assertEqual(demoted.status_code, 200, demoted.data)
        self.assertFalse(demoted.data['is_admin'])
        self.user.tracker_profile.refresh_from_db()
        self.assertFalse(self.user.tracker_profile.is_admin)

    def test_reset_password_returns_new_password_and_revokes_existing_sessions(self):
        user_login = self._login('jane.smith', 'UserPassword123!')
        old_token = user_login['token']

        self._authenticate_admin()
        reset = self.client.post(f'/api/auth/accounts/{self.user.id}/reset-password/', {}, format='json')
        self.assertEqual(reset.status_code, 200, reset.data)
        new_password = reset.data['generated_password']
        self.assertTrue(new_password)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password('UserPassword123!'))

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_token}')
        revoked = self.client.get('/api/auth/me/')
        self.assertEqual(revoked.status_code, 403)

        self.client.credentials()
        relogin = self._login('jane.smith', new_password)
        self.assertEqual(relogin['user']['username'], 'jane.smith')

    def test_admin_can_delete_another_user(self):
        self._authenticate_admin()
        response = self.client.delete(f'/api/auth/accounts/{self.user.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.id).exists())

    def test_admin_cannot_manage_own_account_with_other_user_actions(self):
        self._authenticate_admin()
        promote = self.client.patch(
            f'/api/auth/accounts/{self.admin.id}/admin/',
            {'is_admin': False},
            format='json',
        )
        reset = self.client.post(f'/api/auth/accounts/{self.admin.id}/reset-password/', {}, format='json')
        delete = self.client.delete(f'/api/auth/accounts/{self.admin.id}/')
        self.assertEqual(promote.status_code, 400)
        self.assertEqual(reset.status_code, 400)
        self.assertEqual(delete.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.id).exists())

    def test_regular_user_cannot_manage_accounts(self):
        user_login = self._login('jane.smith', 'UserPassword123!')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_login['token']}")

        other = User.objects.create_user(username='other.user', password='OtherPassword123!')
        UserProfile.objects.create(user=other)

        promote = self.client.patch(
            f'/api/auth/accounts/{other.id}/admin/',
            {'is_admin': True},
            format='json',
        )
        reset = self.client.post(f'/api/auth/accounts/{other.id}/reset-password/', {}, format='json')
        delete = self.client.delete(f'/api/auth/accounts/{other.id}/')
        self.assertEqual(promote.status_code, 403)
        self.assertEqual(reset.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.assertTrue(User.objects.filter(pk=other.id).exists())


class SelfPasswordChangeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='jane.smith',
            password='UserPassword123!',
            first_name='Jane',
            last_name='Smith',
        )
        UserProfile.objects.create(user=self.user, role=UserProfile.ROLE_LAB_TECHNICIAN)

    def _login(self, password='UserPassword123!'):
        response = self.client.post('/api/auth/login/', {
            'username': 'jane.smith',
            'password': password,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def _authenticate(self):
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['token']}")
        return login

    def test_user_can_change_own_password_and_stays_signed_in(self):
        first_login = self._authenticate()
        first_token = first_login['token']

        self.client.credentials()
        second_login = self._login()
        second_token = second_login['token']

        # Change the password using the first session. The second session
        # should be revoked, while this first session stays authenticated.
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {first_token}')
        response = self.client.post('/api/auth/me/password/', {
            'current_password': 'UserPassword123!',
            'new_password': 'UpdatedPassword456!',
            'confirm_password': 'UpdatedPassword456!',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('UpdatedPassword456!'))
        self.assertFalse(self.user.check_password('UserPassword123!'))

        # The session that changed the password remains valid.
        me = self.client.get('/api/auth/me/')
        self.assertEqual(me.status_code, 200, me.data)
        self.assertEqual(me.data['username'], 'jane.smith')

        # Other active sessions are revoked.
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {second_token}')
        revoked = self.client.get('/api/auth/me/')
        self.assertEqual(revoked.status_code, 403)

        self.client.credentials()
        old_login = self.client.post('/api/auth/login/', {
            'username': 'jane.smith',
            'password': 'UserPassword123!',
        }, format='json')
        self.assertEqual(old_login.status_code, 401)
        self._login('UpdatedPassword456!')

    def test_current_password_is_required_and_must_be_correct(self):
        self._authenticate()
        missing = self.client.post('/api/auth/me/password/', {
            'current_password': '',
            'new_password': 'UpdatedPassword456!',
            'confirm_password': 'UpdatedPassword456!',
        }, format='json')
        wrong = self.client.post('/api/auth/me/password/', {
            'current_password': 'WrongPassword123!',
            'new_password': 'UpdatedPassword456!',
            'confirm_password': 'UpdatedPassword456!',
        }, format='json')
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(wrong.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('UserPassword123!'))

    def test_new_password_must_match_and_be_at_least_twelve_characters(self):
        self._authenticate()
        mismatch = self.client.post('/api/auth/me/password/', {
            'current_password': 'UserPassword123!',
            'new_password': 'UpdatedPassword456!',
            'confirm_password': 'DifferentPassword789!',
        }, format='json')
        short = self.client.post('/api/auth/me/password/', {
            'current_password': 'UserPassword123!',
            'new_password': 'Short123!',
            'confirm_password': 'Short123!',
        }, format='json')
        reused = self.client.post('/api/auth/me/password/', {
            'current_password': 'UserPassword123!',
            'new_password': 'UserPassword123!',
            'confirm_password': 'UserPassword123!',
        }, format='json')
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(short.status_code, 400)
        self.assertEqual(reused.status_code, 400)
