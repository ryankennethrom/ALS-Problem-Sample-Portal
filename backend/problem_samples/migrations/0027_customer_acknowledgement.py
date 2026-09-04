import secrets
import uuid
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def generate_acknowledgement_code():
    """Historical six-digit customer code generator used by this migration only."""
    return f"{secrets.randbelow(1_000_000):06d}"


class Migration(migrations.Migration):

    dependencies = [
        ('problem_samples', '0026_allow_zero_expiration_period'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemtable',
            name='acknowledgement_link_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='How many days an acknowledged customer link continues to show the acknowledgement confirmation.',
                validators=[MinValueValidator(0), MaxValueValidator(3650)],
            ),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='acknowledged_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='acknowledgement_code',
            field=models.CharField(default=generate_acknowledgement_code, editable=False, max_length=6),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='acknowledgement_token',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
        migrations.AlterField(
            model_name='problemhistory',
            name='action',
            field=models.CharField(choices=[('created', 'Created'), ('updated', 'Saved changes'), ('comment', 'Added comment'), ('customer_notification', 'Customer notification sent'), ('acknowledged', 'Customer acknowledged notification')], max_length=30),
        ),
    ]
