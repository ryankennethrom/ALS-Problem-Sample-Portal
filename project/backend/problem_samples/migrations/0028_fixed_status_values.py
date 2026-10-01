from django.db import migrations


FIXED_STATUSES = [
    'Customer not yet contacted',
    'Customer emailed by system',
    'Problem acknowledged by customer',
    'To be Disposed',
    'Disposed',
    'Shipped back to client',
]


def normalize_statuses(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    # Lock every table's built-in Status column to the six fixed values.
    for table in ProblemTable.objects.all():
        status_column = ProblemColumn.objects.filter(table=table, field_key='status').first()
        if status_column:
            status_column.name = 'Status'
            status_column.description = 'Current workflow status of the problem sample.'
            status_column.column_type = 'choice'
            status_column.required = True
            status_column.searchable = True
            status_column.include_in_customer_notification = False
            status_column.choices = list(FIXED_STATUSES)
            status_column.default_value = 'Customer not yet contacted'
            status_column.position = 1
            status_column.is_system = True
            status_column.save()

    # Convert every existing sample, including any legacy row without a table.
    # Old/custom statuses are inferred from the notification/acknowledgement state
    # so no row is left with a value outside the new fixed vocabulary.
    for sample in ProblemSample.objects.all():
        values = dict(sample.custom_values or {})
        old = str(values.get('status') or sample.status or '').strip()
        folded = old.casefold()

        if folded == 'disposed':
            new = 'Disposed'
        elif folded == 'to be disposed':
            new = 'To be Disposed'
        elif folded == 'shipped back to client':
            new = 'Shipped back to client'
        elif sample.acknowledged_at:
            new = 'Problem acknowledged by customer'
        elif sample.customer_notified_at or folded in {'notified', 'customer emailed by system'}:
            new = 'Customer emailed by system'
        else:
            new = 'Customer not yet contacted'

        if old != new or values.get('status') != new or sample.status != new:
            values['status'] = new
            sample.custom_values = values
            sample.status = new
            sample.save(update_fields=['custom_values', 'status'])


def noop_reverse(apps, schema_editor):
    # The former custom/free-form status vocabulary cannot be reconstructed reliably.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0027_customer_acknowledgement'),
    ]

    operations = [
        migrations.RunPython(normalize_statuses, noop_reverse),
        migrations.RemoveField(
            model_name='problemtable',
            name='custom_statuses',
        ),
    ]
