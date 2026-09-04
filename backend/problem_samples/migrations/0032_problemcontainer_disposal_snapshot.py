from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0031_purge_expired_acknowledgement_credentials'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemcontainer',
            name='disposal_snapshot',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Rollback state captured immediately before the current container disposal.',
            ),
        ),
    ]
