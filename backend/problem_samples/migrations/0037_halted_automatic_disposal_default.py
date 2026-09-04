from django.db import migrations, models


HALTED = 'Halted Automatic Disposal'
AUTOMATIC = 'Automatically Disposed'


def forward(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key='status').update(default_value=HALTED)


def reverse(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key='status').update(default_value=AUTOMATIC)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0036_automatic_disposal_statuses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='status',
            field=models.CharField(
                blank=True,
                db_index=True,
                default=HALTED,
                max_length=80,
            ),
        ),
        migrations.RunPython(forward, reverse),
    ]
