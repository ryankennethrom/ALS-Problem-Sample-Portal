from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0019_recent_row_modifier_column_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemhistory',
            name='action',
            field=models.CharField(
                choices=[
                    ('created', 'Created'),
                    ('updated', 'Saved changes'),
                    ('comment', 'Added comment'),
                    ('customer_notification', 'Customer notification sent'),
                ],
                max_length=30,
            ),
        ),
    ]
