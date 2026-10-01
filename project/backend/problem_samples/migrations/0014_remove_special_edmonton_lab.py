from django.db import migrations


def remove_special_lab_columns(apps, schema_editor):
    ProblemColumn = apps.get_model("problem_samples", "ProblemColumn")
    ProblemColumn.objects.filter(field_key="lab", is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("problem_samples", "0013_prioritized_client_email_dependencies"),
    ]

    operations = [
        migrations.RunPython(remove_special_lab_columns, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="problemsample",
            name="lab",
        ),
    ]
