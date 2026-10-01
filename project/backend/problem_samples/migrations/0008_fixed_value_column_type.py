from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('problem_samples', '0007_problem_history'),
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
                ],
                default='text',
                max_length=30,
            ),
        ),
    ]
