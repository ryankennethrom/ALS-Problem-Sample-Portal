from django.db import migrations


REACTIVATED_STATUSES = {
    'Automatically Disposed',
    'Halted Automatic Disposal',
}


def reactivate_tracking_links(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    # Historical rows may still carry an expiry anchor created before the
    # lifecycle rule changed. If the row is currently back in one of the active
    # follow-up statuses, the persistent tracking link should be accessible now.
    for sample in ProblemSample.objects.exclude(acknowledgement_status_changed_at=None).iterator():
        values = sample.custom_values or {}
        current_status = str(values.get('status') or sample.status or '').strip()
        if current_status in REACTIVATED_STATUSES:
            sample.acknowledgement_status_changed_at = None
            sample.save(update_fields=['acknowledgement_status_changed_at'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0045_tracking_link_fields_and_persistent_lifecycle'),
    ]

    operations = [
        migrations.RunPython(reactivate_tracking_links, migrations.RunPython.noop),
    ]
