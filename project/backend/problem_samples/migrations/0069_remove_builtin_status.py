from django.db import migrations


def remove_builtin_status_data(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemContainer = apps.get_model('problem_samples', 'ProblemContainer')

    status_columns = list(ProblemColumn.objects.filter(field_key='status'))
    status_ids = {str(column.pk) for column in status_columns}

    # Remove Intercolumn Controller rules that referenced the retired Status column.
    if status_ids:
        for column in ProblemColumn.objects.exclude(intercolumn_rules=[]).iterator():
            rules = list(column.intercolumn_rules or [])
            kept = [rule for rule in rules if str(rule.get('other_column_id') or '') not in status_ids]
            if kept != rules:
                column.intercolumn_rules = kept
                column.save(update_fields=['intercolumn_rules'])

    ProblemColumn.objects.filter(field_key='status').delete()

    # Remove the legacy dynamic key and compact column positions by one.
    for sample in ProblemSample.objects.all().iterator():
        values = dict(sample.custom_values or {})
        if 'status' in values:
            values.pop('status', None)
            sample.custom_values = values
            sample.save(update_fields=['custom_values'])

    for container in ProblemContainer.objects.exclude(disposal_snapshot={}).iterator():
        snapshot = dict(container.disposal_snapshot or {})
        changed = False
        for key, saved in list(snapshot.items()):
            if key.startswith('_') or not isinstance(saved, dict):
                continue
            if 'status' in saved:
                saved.pop('status', None)
                changed = True
            custom = dict(saved.get('custom_values') or {})
            if 'status' in custom:
                custom.pop('status', None)
                saved['custom_values'] = custom
                changed = True
        if changed:
            container.disposal_snapshot = snapshot
            container.save(update_fields=['disposal_snapshot'])

    for column in ProblemColumn.objects.filter(position__gte=2).iterator():
        column.position = max(1, column.position - 1)
        column.save(update_fields=['position'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0068_remove_problemsample_customer_action_and_more'),
    ]

    operations = [
        migrations.RunPython(remove_builtin_status_data, migrations.RunPython.noop),
        migrations.RemoveField(model_name='problemsample', name='status'),
    ]
