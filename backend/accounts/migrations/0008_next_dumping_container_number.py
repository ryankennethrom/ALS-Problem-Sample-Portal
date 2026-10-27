"""Track per-lab dumping-container numbers independently of physical containers."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0007_lab')]
    operations = [
        migrations.AddField(
            model_name='lab',
            name='next_dumping_container_number',
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
