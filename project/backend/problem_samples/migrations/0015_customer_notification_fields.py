import re
from django.db import migrations, models


def normalize_label(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def seed_existing_notification_fields(apps, schema_editor):
    ProblemColumn = apps.get_model("problem_samples", "ProblemColumn")

    # Preserve the useful details that the previous email composer selected
    # automatically. Other fields stay opt-in so internal data is not exposed
    # to customers unless a table owner deliberately enables it.
    patterns = [
        re.compile(r"^status$"),
        re.compile(r"\bdate\b.*\breceived\b|\breceived\b.*\bdate\b"),
        re.compile(r"\bals\b.*\bsample\b.*\btracking\b|\bsample\b.*\btracking\b"),
        re.compile(r"\bnumber\b.*\bproblem\b.*\bsamples?\b|\bproblem\b.*\bsamples?\b.*\bshipment\b"),
        re.compile(r"\bproblem\b.*\btype\b"),
        re.compile(r"\bissue\b.*\bdescription\b|\bproblem\b.*\bdescription\b"),
        re.compile(r"\bcourier\b.*\btracking\b"),
        re.compile(r"^courier$"),
    ]

    for column in ProblemColumn.objects.filter(is_system=False).iterator():
        labels = [normalize_label(column.name), normalize_label(column.field_key), normalize_label(f"{column.name} {column.field_key}")]
        if any(pattern.search(label) for pattern in patterns for label in labels):
            ProblemColumn.objects.filter(pk=column.pk).update(include_in_customer_notification=True)


class Migration(migrations.Migration):
    dependencies = [
        ("problem_samples", "0014_remove_special_edmonton_lab"),
    ]

    operations = [
        migrations.AddField(
            model_name="problemcolumn",
            name="include_in_customer_notification",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(seed_existing_notification_fields, migrations.RunPython.noop),
    ]
