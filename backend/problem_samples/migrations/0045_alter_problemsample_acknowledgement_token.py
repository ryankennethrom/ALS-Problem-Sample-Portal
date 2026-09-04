from django.db import migrations, models


class Migration(migrations.Migration):
    """Keep the acknowledgement/tracking token model state in sync.

    This migration existed on one development branch before the tracking-link
    lifecycle migrations were added. Keeping it in the canonical graph lets
    databases that have seen either branch converge safely.
    """

    dependencies = [
        ('problem_samples', '0044_remove_customer_access_code_hold_sample'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='acknowledgement_token',
            field=models.CharField(
                blank=True,
                default=None,
                editable=False,
                max_length=128,
                null=True,
                unique=True,
            ),
        ),
    ]
