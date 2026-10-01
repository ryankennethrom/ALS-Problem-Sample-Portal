from django.db import migrations, models


DEFAULT_WORKFLOW = 'Follow Up Required'
WORKFLOWS = [
    DEFAULT_WORKFLOW,
    'To be Disposed',
    'To be shipped back to client',
    'To be back to testing',
    'Back to testing',
    'Disposed',
    'Shipped back to client',
]
TERMINAL_WORKFLOWS = set(WORKFLOWS[1:])
CURRENT_WORKFLOW_KEY = 'current-workflow'
DISPOSE_KEY = 'dispose-automatically'
DAYS_KEY = 'system-days-until-automatic-disposal'
TRACKING_LINK_KEY = 'system-tracking-link'
TRACKING_EXPIRY_KEY = 'system-tracking-link-expiry'
LEGACY_AUTOMATIC = {'Automatically Disposed', 'Halted Automatic Disposal'}


def _status_value(sample):
    values = sample.custom_values or {}
    return str(values.get('status') or sample.status or '').strip()


def _clean_status_choices(raw):
    reserved = {value.casefold() for value in TERMINAL_WORKFLOWS | LEGACY_AUTOMATIC}
    result = []
    seen = set()
    for raw_value in raw or []:
        value = str(raw_value or '').strip()
        folded = value.casefold()
        if not value or folded in reserved or folded in seen:
            continue
        result.append(value)
        seen.add(folded)
    return result


def forwards(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemContainer = apps.get_model('problem_samples', 'ProblemContainer')

    workflow_by_fold = {value.casefold(): value for value in WORKFLOWS}
    terminal_folds = {value.casefold() for value in TERMINAL_WORKFLOWS}
    legacy_automatic_folds = {value.casefold() for value in LEGACY_AUTOMATIC}

    for table in ProblemTable.objects.all().iterator():
        samples = list(ProblemSample.objects.filter(table=table).only(
            'id', 'status', 'current_workflow', 'custom_values'
        ))
        status_column = ProblemColumn.objects.filter(table=table, field_key='status').first()
        custom_statuses = _clean_status_choices(status_column.choices if status_column else [])
        seen = {value.casefold() for value in custom_statuses}

        # Preserve all descriptive/non-workflow row statuses that already exist.
        for sample in samples:
            old_status = _status_value(sample)
            folded = old_status.casefold()
            if old_status and folded not in terminal_folds and folded not in legacy_automatic_folds and folded not in seen:
                custom_statuses.append(old_status)
                seen.add(folded)

        if DEFAULT_WORKFLOW.casefold() not in seen:
            custom_statuses.insert(0, DEFAULT_WORKFLOW)
            seen.add(DEFAULT_WORKFLOW.casefold())
        if not custom_statuses:
            custom_statuses = [DEFAULT_WORKFLOW]

        current_default = str(getattr(status_column, 'default_value', '') or '').strip() if status_column else ''
        status_by_fold = {value.casefold(): value for value in custom_statuses}
        status_default = status_by_fold.get(current_default.casefold(), custom_statuses[0])

        if status_column is None:
            status_column = ProblemColumn.objects.create(
                table=table,
                name='Status',
                description='Required descriptive status for this problem sample. Custom values can be managed in Table Settings; workflow routing is controlled separately by Current Workflow.',
                field_key='status',
                column_type='choice',
                required=True,
                searchable=True,
                include_in_customer_notification=False,
                choices=custom_statuses,
                default_value=status_default,
                position=1,
                is_system=True,
            )
        else:
            status_column.name = 'Status'
            status_column.description = 'Required descriptive status for this problem sample. Custom values can be managed in Table Settings; workflow routing is controlled separately by Current Workflow.'
            status_column.column_type = 'choice'
            status_column.required = True
            status_column.searchable = True
            status_column.include_in_customer_notification = False
            status_column.choices = custom_statuses
            status_column.default_value = status_default
            status_column.position = 1
            status_column.is_system = True
            status_column.save()

        workflow_column = ProblemColumn.objects.filter(table=table, field_key=CURRENT_WORKFLOW_KEY).first()
        if workflow_column is None:
            # Before this migration, custom columns begin after the five built-ins.
            # Move them one slot right to make room at position 2.
            for column in ProblemColumn.objects.filter(table=table, is_system=False, position__gte=2):
                column.position += 1
                column.save(update_fields=['position'])
            workflow_column = ProblemColumn.objects.create(
                table=table,
                name='Current Workflow',
                description='Required built-in routing state used by Follow Up Required, disposal, shipping, back-to-testing, customer tracking, and automatic disposal.',
                field_key=CURRENT_WORKFLOW_KEY,
                column_type='choice',
                required=True,
                searchable=True,
                include_in_customer_notification=False,
                choices=WORKFLOWS,
                default_value=DEFAULT_WORKFLOW,
                position=2,
                is_system=True,
            )
        else:
            workflow_column.name = 'Current Workflow'
            workflow_column.description = 'Required built-in routing state used by Follow Up Required, disposal, shipping, back-to-testing, customer tracking, and automatic disposal.'
            workflow_column.column_type = 'choice'
            workflow_column.required = True
            workflow_column.searchable = True
            workflow_column.include_in_customer_notification = False
            workflow_column.choices = WORKFLOWS
            workflow_column.default_value = DEFAULT_WORKFLOW
            workflow_column.position = 2
            workflow_column.is_system = True
            workflow_column.save()

        canonical_positions = {
            DISPOSE_KEY: 3,
            DAYS_KEY: 4,
            TRACKING_LINK_KEY: 5,
            TRACKING_EXPIRY_KEY: 6,
        }
        for key, position in canonical_positions.items():
            ProblemColumn.objects.filter(table=table, field_key=key).update(position=position)

        for sample in samples:
            values = dict(sample.custom_values or {})
            old_status = _status_value(sample)
            folded = old_status.casefold()
            workflow = workflow_by_fold.get(folded, DEFAULT_WORKFLOW)
            descriptive_status = old_status
            if workflow != DEFAULT_WORKFLOW or folded in legacy_automatic_folds or not descriptive_status:
                descriptive_status = status_default
            if descriptive_status.casefold() not in status_by_fold:
                descriptive_status = status_default

            values['status'] = descriptive_status
            values[CURRENT_WORKFLOW_KEY] = workflow
            if workflow in TERMINAL_WORKFLOWS:
                values[DISPOSE_KEY] = 'No'

            sample.status = descriptive_status
            sample.current_workflow = workflow
            sample.custom_values = values
            sample.save(update_fields=['status', 'current_workflow', 'custom_values'])

    # Normalize disposal rollback snapshots so undo restores workflow separately
    # from descriptive Status after this migration.
    sample_map = {
        str(sample.id): sample
        for sample in ProblemSample.objects.only('id', 'status', 'current_workflow', 'custom_values')
    }
    for container in ProblemContainer.objects.exclude(disposal_snapshot={}).iterator():
        snapshot = dict(container.disposal_snapshot or {})
        changed = False
        for sample_id, saved in list(snapshot.items()):
            if not isinstance(saved, dict):
                continue
            saved = dict(saved)
            custom = dict(saved.get('custom_values') or {})
            raw_status = str(custom.get('status') or saved.get('status') or '').strip()
            workflow = workflow_by_fold.get(raw_status.casefold(), DEFAULT_WORKFLOW)
            sample = sample_map.get(str(sample_id))
            descriptive = raw_status
            if workflow != DEFAULT_WORKFLOW and sample is not None:
                descriptive = sample.status
            custom['status'] = descriptive
            custom[CURRENT_WORKFLOW_KEY] = workflow
            saved['status'] = descriptive
            saved['current_workflow'] = workflow
            saved['custom_values'] = custom
            snapshot[sample_id] = saved
            changed = True
        if changed:
            container.disposal_snapshot = snapshot
            container.save(update_fields=['disposal_snapshot'])


def backwards(apps, schema_editor):
    # Current Workflow information cannot be safely folded back into arbitrary
    # custom Status values after users have edited Status independently.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0050_emailtemplate'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemsample',
            name='current_workflow',
            field=models.CharField(db_index=True, default=DEFAULT_WORKFLOW, max_length=80),
        ),
        migrations.RunPython(forwards, backwards),
    ]
