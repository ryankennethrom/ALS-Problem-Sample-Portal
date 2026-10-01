import uuid
from django.db import migrations


SYSTEM_STATUSES = [
    'Disposed',
    'To Be Disposed',
    'Notified',
    'Not Notified',
    'In Progress',
]
RESERVED = {value.casefold() for value in SYSTEM_STATUSES}
OLD_WAITING = 'Waiting For Response'


def update_statuses(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    for table in ProblemTable.objects.all().iterator():
        # Keep user-created statuses, but system-reserved labels are no longer stored
        # in the custom list. The retired Waiting For Response value is removed.
        cleaned_custom = []
        seen_custom = set()
        for item in table.custom_statuses or []:
            if isinstance(item, dict):
                label = str(item.get('label') or '').strip()
                status_id = item.get('id')
            else:
                label = str(item or '').strip()
                status_id = None
            folded = label.casefold()
            if not label or folded in RESERVED or folded == OLD_WAITING.casefold() or folded in seen_custom:
                continue
            cleaned_custom.append({'id': str(status_id or uuid.uuid4()), 'label': label})
            seen_custom.add(folded)

        # Replace the retired status using the actual notification state where possible.
        # This avoids treating rows that were never emailed as already notified.
        for sample in ProblemSample.objects.filter(table_id=table.id).iterator():
            values = dict(sample.custom_values or {})
            current = str(values.get('status') or sample.status or '').strip()
            if not current or current.casefold() == OLD_WAITING.casefold():
                current = 'Notified' if sample.customer_notified_at else 'Not Notified'
                values['status'] = current
                ProblemSample.objects.filter(pk=sample.pk).update(custom_values=values, status=current)

        ProblemTable.objects.filter(pk=table.pk).update(custom_statuses=cleaned_custom)
        choices = SYSTEM_STATUSES + [item['label'] for item in cleaned_custom]
        ProblemColumn.objects.filter(table_id=table.id, field_key='status').update(
            name='Status',
            column_type='choice',
            required=True,
            searchable=True,
            choices=choices,
            default_value='Not Notified',
            position=1,
            is_system=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0024_status_disposal_workflow'),
    ]

    operations = [
        migrations.RunPython(update_statuses, migrations.RunPython.noop),
    ]
