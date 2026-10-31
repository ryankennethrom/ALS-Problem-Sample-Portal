from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0098_brand_email_rules')]

    operations = [
        migrations.AddField(
            model_name='problemtable',
            name='terminal_tracking_link_days',
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
                default=30,
                validators=[MinValueValidator(0), MaxValueValidator(3650)],
                help_text=(
                    'How many days a tracking link remains active after entering a completed '
                    'terminal workflow (Back to Testing, Disposed, Shipped Back to Client). '
                    'Null means never expire. Changes affect future workflow transitions only.'
                ),
            ),
        ),
    ]
