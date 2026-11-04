"""Allow immediate Client Email priority escalation (0 hours)."""
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0103_reconcile_legacy_tracking_send_history')]

    operations = [
        migrations.AlterField(
            model_name='problemcolumn',
            name='client_email_fallback_hours',
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
                validators=[MinValueValidator(0), MaxValueValidator(87600)],
                help_text='After this many hours without a new customer response, escalate to the next priority.',
            ),
        ),
    ]
