from django.db import migrations
from django.utils import timezone


def revoke_existing_sessions(apps, schema_editor):
    AppSession = apps.get_model('accounts', 'AppSession')
    AppSession.objects.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_userprofile_is_admin'),
    ]

    operations = [
        migrations.RunPython(revoke_existing_sessions, migrations.RunPython.noop),
    ]
