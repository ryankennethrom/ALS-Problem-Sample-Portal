from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0053_intercolumn_value_controller'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemtable',
            name='pt_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Automatic-disposal expiration period in days from the most recent change of Dispose Automatically from No to Yes. When the period ends, Current Workflow changes to To be Disposed. Zero means an immediate transition.',
                validators=[MinValueValidator(0), MaxValueValidator(3650)],
            ),
        ),
    ]
