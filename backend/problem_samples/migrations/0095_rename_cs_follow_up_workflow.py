"""Rename the active follow-up routing value while preserving existing tickets.

Historical migrations must stay unchanged. This follows the two 0093 branches
joined by 0094 and updates existing data, column choices and disposal snapshots.
Ticket histories remain untouched because they are audit records of past actions.
"""

from django.db import migrations, models


OLD_WORKFLOW = 'CS Follow-Up'
NEW_WORKFLOW = 'Follow Up Required'
WORKFLOW_KEY = 'current-workflow'


def replace_exact(value, previous, updated):
    """Replace a workflow label in nested configuration without altering other text."""
    if isinstance(value, str):
        return updated if value == previous else value
    if isinstance(value, list):
        return [replace_exact(item, previous, updated) for item in value]
    if isinstance(value, dict):
        return {key: replace_exact(item, previous, updated) for key, item in value.items()}
    return value


def rename_workflow(apps, previous, updated):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemContainer = apps.get_model('problem_samples', 'ProblemContainer')

    # The indexed routing field and the table's dynamic workflow value must agree.
    ProblemSample.objects.filter(current_workflow=previous).update(current_workflow=updated)
    for ticket in ProblemSample.objects.all().only('id', 'custom_values').iterator():
        values = dict(ticket.custom_values or {})
        if values.get(WORKFLOW_KEY) == previous:
            values[WORKFLOW_KEY] = updated
            ProblemSample.objects.filter(pk=ticket.pk).update(custom_values=values)

    # Every table has its own built-in Current Workflow column definition.
    for column in ProblemColumn.objects.filter(field_key=WORKFLOW_KEY).iterator():
        updates = []
        choices = replace_exact(column.choices or [], previous, updated)
        if choices != column.choices:
            column.choices = list(dict.fromkeys(choices))
            updates.append('choices')
        if column.default_value == previous:
            column.default_value = updated
            updates.append('default_value')
        description = (column.description or '').replace(previous, updated)
        if description != column.description:
            column.description = description
            updates.append('description')
        if updates:
            column.save(update_fields=updates)

    # Custom intercolumn rules may compare or assign a workflow choice.
    for column in ProblemColumn.objects.exclude(intercolumn_rules=[]).iterator():
        rules = replace_exact(column.intercolumn_rules or [], previous, updated)
        if rules != column.intercolumn_rules:
            column.intercolumn_rules = rules
            column.save(update_fields=['intercolumn_rules'])

    # Disposal rollback snapshots also store workflow values. If skipped, undoing
    # a disposal could reintroduce the retired value to a live ticket.
    for container in ProblemContainer.objects.exclude(disposal_snapshot={}).iterator():
        snapshot = dict(container.disposal_snapshot or {})
        changed = False
        for ticket_id, saved_value in snapshot.items():
            if not isinstance(saved_value, dict):
                continue
            saved = dict(saved_value)
            values = dict(saved.get('custom_values') or {})
            if saved.get('current_workflow') == previous:
                saved['current_workflow'] = updated
            if values.get(WORKFLOW_KEY) == previous:
                values[WORKFLOW_KEY] = updated
                saved['custom_values'] = values
            if saved != saved_value:
                snapshot[ticket_id] = saved
                changed = True
        if changed:
            container.disposal_snapshot = snapshot
            container.save(update_fields=['disposal_snapshot'])


def forwards(apps, schema_editor):
    rename_workflow(apps, OLD_WORKFLOW, NEW_WORKFLOW)


def backwards(apps, schema_editor):
    rename_workflow(apps, NEW_WORKFLOW, OLD_WORKFLOW)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0094_merge_customer_return_label'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='current_workflow',
            field=models.CharField(db_index=True, default=NEW_WORKFLOW, max_length=80),
        ),
        migrations.RunPython(forwards, backwards),
    ]
