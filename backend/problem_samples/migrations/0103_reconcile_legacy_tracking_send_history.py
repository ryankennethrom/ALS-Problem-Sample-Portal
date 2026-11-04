"""Reconcile legacy tracking-send timestamps after migrations/restores.

Full database restores can reintroduce older records after 0102 has already
been applied. Running the same idempotent backfill again does not change ticket
workflow, email priority, disposal deadlines, or history entries.
"""
import importlib
from django.db import migrations


def reconcile_legacy_history(apps, schema_editor):
    previous = importlib.import_module(
        'problem_samples.migrations.0102_backfill_client_email_priority_history'
    )
    previous.backfill_from_history(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0102_backfill_client_email_priority_history')]
    operations = [migrations.RunPython(reconcile_legacy_history, migrations.RunPython.noop)]
