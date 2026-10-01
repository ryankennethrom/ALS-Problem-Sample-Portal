from django.db import migrations, models


def copy_existing_tokens(apps, schema_editor):
    ProblemSample = apps.get_model("problem_samples", "ProblemSample")
    for problem in ProblemSample.objects.exclude(acknowledgement_token__isnull=True).iterator():
        # The historical UUIDField materializes as a UUID object. Store its canonical
        # string representation so already-sent acknowledgement URLs keep working.
        problem.acknowledgement_token_secure = str(problem.acknowledgement_token)
        problem.save(update_fields=["acknowledgement_token_secure"])


class Migration(migrations.Migration):

    dependencies = [
        ("problem_samples", "0042_customer_acknowledged_problem_sample_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="problemsample",
            name="acknowledgement_token_secure",
            field=models.CharField(blank=True, editable=False, max_length=128, null=True),
        ),
        migrations.RunPython(copy_existing_tokens, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="problemsample",
            name="acknowledgement_token",
        ),
        migrations.RenameField(
            model_name="problemsample",
            old_name="acknowledgement_token_secure",
            new_name="acknowledgement_token",
        ),
        migrations.AlterField(
            model_name="problemsample",
            name="acknowledgement_token",
            field=models.CharField(blank=True, editable=False, max_length=128, null=True, unique=True),
        ),
    ]
