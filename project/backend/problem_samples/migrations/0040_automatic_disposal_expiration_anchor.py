from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


AUTOMATIC = 'Automatically Disposed'
FIELD_KEY = 'system-days-until-automatic-disposal'
DESCRIPTION = (
    'Read-only countdown until this sample becomes automatically eligible for disposal. '
    'The countdown restarts whenever Status changes to Automatically Disposed and applies '
    'only while that status is active.'
)


def seed_anchors_and_description(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')

    # Existing rows did not store the moment automatic disposal was activated.
    # For rows currently in that status, the first confirmed notification is the
    # best available activation time because that workflow was what switched the
    # status in the immediately preceding version. Fall back to modified/created.
    for sample in ProblemSample.objects.filter(status=AUTOMATIC).iterator():
        values = sample.custom_values or {}
        workflow_status = str(values.get('status') or sample.status or '').strip()
        if workflow_status != AUTOMATIC:
            continue
        anchor = sample.customer_notified_at or sample.modified_at or sample.created_at
        if anchor:
            ProblemSample.objects.filter(pk=sample.pk).update(automatic_disposal_started_at=anchor)

    ProblemColumn.objects.filter(field_key=FIELD_KEY).update(description=DESCRIPTION)


def reverse_seed(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key=FIELD_KEY).update(
        description='Read-only countdown until this sample becomes automatically eligible for disposal. The countdown is based on Date Created plus the problem sample expiration period and applies only while Status is Automatically Disposed.'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0039_expiration_from_date_created'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemsample',
            name='automatic_disposal_started_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='problemtable',
            name='pt_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Automatic-disposal expiration period in days from the most recent transition into Automatically Disposed. Zero means immediate eligibility when automatic disposal is activated.',
                validators=[MinValueValidator(0), MaxValueValidator(3650)],
            ),
        ),
        migrations.RunPython(seed_anchors_and_description, reverse_seed),
    ]
