from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0020_customer_notification_history_action'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemcolumn',
            name='column_type',
            field=models.CharField(
                choices=[
                    ('text', 'Single line of text'),
                    ('long_text', 'Multiple lines of text'),
                    ('number', 'Number'),
                    ('choice', 'Choice'),
                    ('multi_choice', 'Multiple choice'),
                    ('date', 'Date'),
                    ('datetime', 'Date and time'),
                    ('time', 'Time'),
                    ('boolean', 'Yes / No'),
                    ('email', 'Email'),
                    ('url', 'URL'),
                    ('fixed', 'Fixed Value'),
                    ('group', 'Group'),
                    ('distributor', 'Distributor'),
                    ('end_user', 'End User'),
                    ('brand', 'Brand'),
                    ('client_email', 'Client Email'),
                    ('row_creator', 'Row Creator'),
                    ('recent_row_modifier', 'Recent Row Modifier'),
                ],
                default='text',
                max_length=30,
            ),
        ),
    ]
