from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0074_date_today_column_type'),
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
                    ('date_today', 'Date (Today)'),
                    ('datetime', 'Date and time'),
                    ('time', 'Time'),
                    ('boolean', 'Yes / No'),
                    ('email', 'Email'),
                    ('phone', 'Phone Number'),
                    ('url', 'URL'),
                    ('fixed', 'Fixed Value'),
                    ('group', 'Group'),
                    ('distributor', 'Distributor'),
                    ('end_user', 'End User'),
                    ('brand', 'Brand'),
                    ('client_email', 'Client Email'),
                    ('row_creator', 'Row Creator'),
                    ('recent_row_modifier', 'Recent Row Modifier'),
                    ('intercolumn_controller', 'Intercolumn Value Controller'),
                ],
                default='text',
                max_length=30,
            ),
        ),
    ]
