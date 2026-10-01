from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


FIELD_KEY = 'system-days-until-automatic-disposal'
DESCRIPTION = (
    'Read-only countdown until this sample becomes automatically eligible for disposal. '
    'The countdown is based on Date Created plus the problem sample expiration period and '
    'applies only while Status is Automatically Disposed.'
)


def forward(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key=FIELD_KEY).update(description=DESCRIPTION)


def reverse(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key=FIELD_KEY).update(
        description='Read-only countdown until this sample becomes automatically eligible for disposal. The countdown starts after the customer notification is confirmed sent and applies only while Status is Automatically Disposed.'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0038_builtin_days_until_automatic_disposal'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemtable',
            name='pt_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Problem sample expiration period in days from the problem sample creation time. Zero means the sample expires immediately when it is created.',
                validators=[MinValueValidator(0), MaxValueValidator(3650)],
            ),
        ),
        migrations.RunPython(forward, reverse),
    ]
