from django.db import migrations, models


def purge_unconfirmed_credentials(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    # customer_notified_at is only set after the user confirms "I sent the email".
    # Any credentials on rows without that confirmation were created by the old
    # automatic field defaults and should not remain accessible.
    ProblemSample.objects.filter(customer_notified_at__isnull=True).update(
        acknowledgement_token=None,
        acknowledgement_code=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0032_problemcontainer_disposal_snapshot'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='acknowledgement_token',
            field=models.UUIDField(blank=True, db_index=True, default=None, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name='problemsample',
            name='acknowledgement_code',
            field=models.CharField(blank=True, default=None, editable=False, max_length=6, null=True),
        ),
        migrations.RunPython(purge_unconfirmed_credentials, migrations.RunPython.noop),
    ]
