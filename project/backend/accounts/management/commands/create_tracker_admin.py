from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.account_utils import derive_unique_username, generate_temporary_password
from accounts.models import UserProfile


class Command(BaseCommand):
    help = 'Create an initial tracker administrator with a derived username and random password.'

    def add_arguments(self, parser):
        parser.add_argument('--first-name', required=True)
        parser.add_argument('--last-name', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        first_name = str(options['first_name'] or '').strip()
        last_name = str(options['last_name'] or '').strip()
        if not first_name or not last_name:
            raise CommandError('First Name and Last Name are required.')

        try:
            username = derive_unique_username(first_name, last_name)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        password = generate_temporary_password()
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email='',
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_admin = True
        profile.save(update_fields=['is_admin', 'modified_at'])

        self.stdout.write(self.style.SUCCESS('Tracker administrator created.'))
        self.stdout.write(f'Username: {username}')
        self.stdout.write(f'Password: {password}')
        self.stdout.write('Store the password securely. It is not recoverable from the database.')
