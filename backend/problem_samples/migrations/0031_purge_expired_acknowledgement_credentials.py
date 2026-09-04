import secrets
import uuid
from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone



def generate_acknowledgement_code():
    """Historical six-digit customer code generator used by this migration only."""
    return f"{secrets.randbelow(1_000_000):06d}"


def purge_already_expired_credentials(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    cutoff = timezone.now() - timedelta(days=30)
    ProblemSample.objects.filter(
        acknowledgement_status_changed_at__isnull=False,
        acknowledgement_status_changed_at__lte=cutoff,
    ).update(acknowledgement_token=None, acknowledgement_code=None)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0030_acknowledgement_link_status_lifecycle'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='acknowledgement_token',
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name='problemsample',
            name='acknowledgement_code',
            field=models.CharField(blank=True, default=generate_acknowledgement_code, editable=False, max_length=6, null=True),
        ),
        migrations.RunPython(purge_already_expired_credentials, migrations.RunPython.noop),
    ]
