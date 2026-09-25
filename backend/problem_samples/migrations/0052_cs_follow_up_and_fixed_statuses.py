from django.db import migrations, models

OLD_WORKFLOW_DEFAULT = 'Follow Up Required'
WORKFLOW_DEFAULT = 'CS Follow-Up'
WORKFLOWS = [
    WORKFLOW_DEFAULT,
    'To be Disposed',
    'To be shipped back to client',
    'To be back to testing',
    'Back to testing',
    'Disposed',
    'Shipped back to client',
]
STATUS_DEFAULT = 'NEW'
STATUSES = ['NEW', 'IN PROGRESS', 'ON HOLD', 'SHIPPED BACK TO CLIENT', 'DISPOSED', 'COMPLETED']
CURRENT_WORKFLOW_KEY = 'current-workflow'
STATUS_KEY = 'status'


def normalize_status(value):
    text = str(value or '').strip()
    folded = text.casefold()
    exact = {item.casefold(): item for item in STATUSES}
    if folded in exact:
        return exact[folded]
    if 'shipped back' in folded:
        return 'SHIPPED BACK TO CLIENT'
    if 'disposed' in folded:
        return 'DISPOSED'
    if folded in {'completed', 'complete', 'resolved', 'closed'}:
        return 'COMPLETED'
    if 'hold' in folded or 'halted' in folded:
        return 'ON HOLD'
    if folded in {
        'in progress', 'notified', 'customer emailed by system', 'problem acknowledged by customer',
        'to be back to testing', 'back to testing', 'to be shipped back to client', 'to be disposed',
    }:
        return 'IN PROGRESS'
    return STATUS_DEFAULT


def normalize_workflow(value):
    text = str(value or '').strip()
    if text.casefold() == OLD_WORKFLOW_DEFAULT.casefold():
        return WORKFLOW_DEFAULT
    by_fold = {item.casefold(): item for item in WORKFLOWS}
    return by_fold.get(text.casefold(), WORKFLOW_DEFAULT)


def forwards(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemContainer = apps.get_model('problem_samples', 'ProblemContainer')

    for table in ProblemTable.objects.all().iterator():
        status_column = ProblemColumn.objects.filter(table=table, field_key=STATUS_KEY).first()
        status_defaults = dict(
            name='Status',
            description='Required built-in descriptive status. Values are fixed across all problem sample tables; workflow routing is controlled separately by Current Workflow.',
            column_type='choice', required=True, searchable=True,
            include_in_customer_notification=False, choices=list(STATUSES),
            default_value=STATUS_DEFAULT, position=1, is_system=True,
        )
        if status_column is None:
            status_column = ProblemColumn.objects.create(table=table, field_key=STATUS_KEY, **status_defaults)
        else:
            for field, value in status_defaults.items():
                setattr(status_column, field, value)
            status_column.save()

        workflow_column = ProblemColumn.objects.filter(table=table, field_key=CURRENT_WORKFLOW_KEY).first()
        workflow_defaults = dict(
            name='Current Workflow',
            description='Required built-in routing state used by CS Follow-Up, disposal, shipping, back-to-testing, customer tracking, and automatic disposal.',
            column_type='choice', required=True, searchable=True,
            include_in_customer_notification=False, choices=list(WORKFLOWS),
            default_value=WORKFLOW_DEFAULT, position=2, is_system=True,
        )
        if workflow_column is None:
            workflow_column = ProblemColumn.objects.create(table=table, field_key=CURRENT_WORKFLOW_KEY, **workflow_defaults)
        else:
            for field, value in workflow_defaults.items():
                setattr(workflow_column, field, value)
            workflow_column.save()

        for sample in ProblemSample.objects.filter(table=table).only('id', 'status', 'current_workflow', 'custom_values').iterator():
            values = dict(sample.custom_values or {})
            status_value = normalize_status(values.get(STATUS_KEY) or sample.status)
            workflow_value = normalize_workflow(values.get(CURRENT_WORKFLOW_KEY) or sample.current_workflow)
            values[STATUS_KEY] = status_value
            values[CURRENT_WORKFLOW_KEY] = workflow_value
            ProblemSample.objects.filter(pk=sample.pk).update(
                status=status_value,
                current_workflow=workflow_value,
                custom_values=values,
            )

    # Keep disposal rollback snapshots compatible with the new fixed Status set
    # and the renamed default workflow.
    for container in ProblemContainer.objects.exclude(disposal_snapshot={}).iterator():
        snapshot = dict(container.disposal_snapshot or {})
        changed = False
        for sample_id, saved_raw in list(snapshot.items()):
            if not isinstance(saved_raw, dict):
                continue
            saved = dict(saved_raw)
            custom = dict(saved.get('custom_values') or {})
            status_value = normalize_status(custom.get(STATUS_KEY) or saved.get('status'))
            workflow_value = normalize_workflow(custom.get(CURRENT_WORKFLOW_KEY) or saved.get('current_workflow'))
            custom[STATUS_KEY] = status_value
            custom[CURRENT_WORKFLOW_KEY] = workflow_value
            saved['status'] = status_value
            saved['current_workflow'] = workflow_value
            saved['custom_values'] = custom
            snapshot[sample_id] = saved
            changed = True
        if changed:
            container.disposal_snapshot = snapshot
            container.save(update_fields=['disposal_snapshot'])


def backwards(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')

    ProblemSample.objects.filter(current_workflow=WORKFLOW_DEFAULT).update(current_workflow=OLD_WORKFLOW_DEFAULT)
    for sample in ProblemSample.objects.all().only('id', 'custom_values').iterator():
        values = dict(sample.custom_values or {})
        if str(values.get(CURRENT_WORKFLOW_KEY) or '').casefold() == WORKFLOW_DEFAULT.casefold():
            values[CURRENT_WORKFLOW_KEY] = OLD_WORKFLOW_DEFAULT
            ProblemSample.objects.filter(pk=sample.pk).update(custom_values=values)
    for column in ProblemColumn.objects.filter(field_key=CURRENT_WORKFLOW_KEY):
        column.choices = [OLD_WORKFLOW_DEFAULT, *WORKFLOWS[1:]]
        column.default_value = OLD_WORKFLOW_DEFAULT
        column.save(update_fields=['choices', 'default_value'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0051_current_workflow'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='status',
            field=models.CharField(blank=True, db_index=True, default=STATUS_DEFAULT, max_length=80),
        ),
        migrations.AlterField(
            model_name='problemsample',
            name='current_workflow',
            field=models.CharField(db_index=True, default=WORKFLOW_DEFAULT, max_length=80),
        ),
        migrations.RunPython(forwards, backwards),
    ]
