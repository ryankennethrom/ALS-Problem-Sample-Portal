from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('problem_samples', '0008_fixed_value_column_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemcolumn',
            name='group_role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('lab_technician', 'Lab Technician'),
                    ('customer_service', 'Customer Service'),
                ],
                max_length=40,
            ),
        ),
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
                ],
                default='text',
                max_length=30,
            ),
        ),
    ]
