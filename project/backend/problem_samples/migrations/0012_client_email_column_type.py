from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0011_end_user_column_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemcolumn',
            name='depends_on_column',
            field=models.ForeignKey(
                blank=True,
                help_text='Optional row field whose value scopes Client Email suggestions to one company.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='dependent_columns',
                to='problem_samples.problemcolumn',
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
                    ('distributor', 'Distributor'),
                    ('end_user', 'End User'),
                    ('client_email', 'Client Email'),
                ],
                default='text',
                max_length=30,
            ),
        ),
    ]
