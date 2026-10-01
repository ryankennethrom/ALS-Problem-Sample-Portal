from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('problem_samples', '0025_notified_statuses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemtable',
            name='pt_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Problem sample expiration period in days from the first confirmed customer notification. Zero means the sample expires immediately when notification is confirmed.',
                validators=[MinValueValidator(0), MaxValueValidator(3650)],
            ),
        ),
    ]
