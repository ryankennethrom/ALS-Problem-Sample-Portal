from django.db import migrations


OLD_NOT_CONTACTED = 'Customer not yet contacted'
OLD_EMAILED = 'Customer emailed by system'
OLD_ACKNOWLEDGED = 'Problem acknowledged by customer'
AUTOMATIC = 'Automatically Disposed'
HALTED = 'Halted Automatic Disposal'

FIXED_STATUSES = [
    AUTOMATIC,
    HALTED,
    'To be Disposed',
    'To be shipped back to client',
    'To be back to testing',
    'Back to testing',
    'Disposed',
    'Shipped back to client',
]


def map_status(value):
    if value in {OLD_NOT_CONTACTED, OLD_EMAILED}:
        return AUTOMATIC
    if value == OLD_ACKNOWLEDGED:
        return HALTED
    return value


def forward(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemContainer = apps.get_model('problem_samples', 'ProblemContainer')

    for column in ProblemColumn.objects.filter(field_key='status'):
        column.choices = list(FIXED_STATUSES)
        column.default_value = AUTOMATIC
        column.save(update_fields=['choices', 'default_value'])

    for sample in ProblemSample.objects.all().iterator():
        changed = []
        mapped_core = map_status(sample.status)
        if mapped_core != sample.status:
            sample.status = mapped_core
            changed.append('status')

        values = dict(sample.custom_values or {})
        if 'status' in values:
            mapped_custom = map_status(values.get('status'))
            if mapped_custom != values.get('status'):
                values['status'] = mapped_custom
                sample.custom_values = values
                changed.append('custom_values')
        if changed:
            sample.save(update_fields=changed)

    # Disposal rollback snapshots can outlive a status migration. Normalize the
    # saved pre-disposal statuses too so Undo Disposal cannot restore a retired
    # workflow value later.
    for container in ProblemContainer.objects.all().iterator():
        snapshot = dict(container.disposal_snapshot or {})
        dirty = False
        for sample_id, saved in list(snapshot.items()):
            if not isinstance(saved, dict):
                continue
            saved = dict(saved)
            mapped = map_status(saved.get('status'))
            if mapped != saved.get('status'):
                saved['status'] = mapped
                dirty = True
            custom = dict(saved.get('custom_values') or {})
            if 'status' in custom:
                mapped_custom = map_status(custom.get('status'))
                if mapped_custom != custom.get('status'):
                    custom['status'] = mapped_custom
                    saved['custom_values'] = custom
                    dirty = True
            snapshot[sample_id] = saved
        if dirty:
            container.disposal_snapshot = snapshot
            container.save(update_fields=['disposal_snapshot'])


def reverse(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')

    old_choices = [
        OLD_NOT_CONTACTED,
        OLD_EMAILED,
        OLD_ACKNOWLEDGED,
        'To be Disposed',
        'To be shipped back to client',
        'To be back to testing',
        'Back to testing',
        'Disposed',
        'Shipped back to client',
    ]
    for column in ProblemColumn.objects.filter(field_key='status'):
        column.choices = old_choices
        column.default_value = OLD_NOT_CONTACTED
        column.save(update_fields=['choices', 'default_value'])

    for sample in ProblemSample.objects.all().iterator():
        changed = []
        if sample.status == AUTOMATIC:
            sample.status = OLD_EMAILED if sample.customer_notified_at else OLD_NOT_CONTACTED
            changed.append('status')
        elif sample.status == HALTED:
            sample.status = OLD_ACKNOWLEDGED
            changed.append('status')

        values = dict(sample.custom_values or {})
        current = values.get('status')
        if current == AUTOMATIC:
            values['status'] = OLD_EMAILED if sample.customer_notified_at else OLD_NOT_CONTACTED
            sample.custom_values = values
            changed.append('custom_values')
        elif current == HALTED:
            values['status'] = OLD_ACKNOWLEDGED
            sample.custom_values = values
            changed.append('custom_values')
        if changed:
            sample.save(update_fields=list(dict.fromkeys(changed)))


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0035_back_to_testing_statuses'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
