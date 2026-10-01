from django.db import migrations, models
import django.core.validators


DEFAULT_STATUS = 'Follow Up Required'
LEGACY_AUTO = 'Automatically Disposed'
LEGACY_HALTED = 'Halted Automatic Disposal'
TERMINAL_STATUSES = [
    'To be Disposed',
    'To be shipped back to client',
    'To be back to testing',
    'Back to testing',
    'Disposed',
    'Shipped back to client',
]
DISPOSE_KEY = 'dispose-automatically'
YES = 'Yes'
NO = 'No'
DAYS_KEY = 'system-days-until-automatic-disposal'
TRACKING_LINK_KEY = 'system-tracking-link'
TRACKING_EXPIRY_KEY = 'system-tracking-link-expiry'


def _clean_custom(values):
    protected = {value.casefold() for value in TERMINAL_STATUSES}
    legacy = {LEGACY_AUTO.casefold(), LEGACY_HALTED.casefold()}
    result = []
    seen = set()
    for raw in values or []:
        value = str(raw or '').strip()
        folded = value.casefold()
        if not value or folded in protected or folded in legacy or folded in seen:
            continue
        result.append(value)
        seen.add(folded)
    return result


def forwards(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    protected = {value.casefold() for value in TERMINAL_STATUSES}
    legacy = {LEGACY_AUTO.casefold(), LEGACY_HALTED.casefold()}

    for table in ProblemTable.objects.all().iterator():
        status_column = ProblemColumn.objects.filter(table=table, field_key='status').first()
        custom = _clean_custom(status_column.choices if status_column else [])
        seen = {value.casefold() for value in custom}

        # Preserve any non-terminal values that may already exist in row data, even
        # if an older Status column definition did not list them explicitly.
        samples = list(ProblemSample.objects.filter(table=table).only(
            'id', 'status', 'custom_values', 'automatic_disposal_started_at', 'created_at', 'modified_at'
        ))
        for sample in samples:
            values = sample.custom_values or {}
            raw_status = str(values.get('status') or sample.status or '').strip()
            folded = raw_status.casefold()
            if raw_status and folded not in protected and folded not in legacy and folded not in seen:
                custom.append(raw_status)
                seen.add(folded)

        if DEFAULT_STATUS.casefold() not in seen:
            custom.insert(0, DEFAULT_STATUS)
            seen.add(DEFAULT_STATUS.casefold())
        if not custom:
            custom = [DEFAULT_STATUS]

        if status_column is None:
            status_column = ProblemColumn.objects.create(
                table=table,
                name='Status',
                description='Current workflow status of the problem sample. Custom non-terminal values can be managed in Table Settings; protected workflow statuses cannot be changed.',
                field_key='status',
                column_type='choice',
                required=True,
                searchable=True,
                include_in_customer_notification=False,
                choices=[*custom, *TERMINAL_STATUSES],
                default_value=custom[0],
                position=1,
                is_system=True,
            )
        else:
            current_default = str(status_column.default_value or '').strip()
            custom_by_fold = {value.casefold(): value for value in custom}
            status_column.name = 'Status'
            status_column.description = 'Current workflow status of the problem sample. Custom non-terminal values can be managed in Table Settings; protected workflow statuses cannot be changed.'
            status_column.column_type = 'choice'
            status_column.required = True
            status_column.searchable = True
            status_column.include_in_customer_notification = False
            status_column.choices = [*custom, *TERMINAL_STATUSES]
            status_column.default_value = custom_by_fold.get(current_default.casefold(), custom[0])
            status_column.position = 1
            status_column.is_system = True
            status_column.save()

        auto_column = ProblemColumn.objects.filter(table=table, field_key=DISPOSE_KEY).first()
        if auto_column is None:
            # Add one slot after Status for the new built-in field. Known system
            # columns are assigned their canonical positions below.
            for column in ProblemColumn.objects.filter(table=table, position__gte=2).exclude(
                field_key__in=[DISPOSE_KEY, DAYS_KEY, TRACKING_LINK_KEY, TRACKING_EXPIRY_KEY]
            ):
                column.position = column.position + 1
                column.save(update_fields=['position'])
            auto_column = ProblemColumn.objects.create(
                table=table,
                name='Dispose Automatically',
                description='Required built-in setting that controls whether the automatic-disposal countdown is active for this problem sample.',
                field_key=DISPOSE_KEY,
                column_type='choice',
                required=True,
                searchable=True,
                include_in_customer_notification=False,
                choices=[YES, NO],
                default_value=NO,
                position=2,
                is_system=True,
            )
        else:
            auto_column.name = 'Dispose Automatically'
            auto_column.description = 'Required built-in setting that controls whether the automatic-disposal countdown is active for this problem sample.'
            auto_column.column_type = 'choice'
            auto_column.required = True
            auto_column.searchable = True
            auto_column.include_in_customer_notification = False
            auto_column.choices = [YES, NO]
            auto_column.default_value = NO
            auto_column.position = 2
            auto_column.is_system = True
            auto_column.save()

        canonical_positions = {
            DAYS_KEY: 3,
            TRACKING_LINK_KEY: 4,
            TRACKING_EXPIRY_KEY: 5,
        }
        for key, position in canonical_positions.items():
            ProblemColumn.objects.filter(table=table, field_key=key).update(position=position)

        # Translate the two legacy automatic-disposal Status values into the new
        # required Yes/No field. Terminal statuses always disable automatic disposal.
        for sample in samples:
            values = dict(sample.custom_values or {})
            old_status = str(values.get('status') or sample.status or '').strip()
            folded = old_status.casefold()
            if folded == LEGACY_AUTO.casefold():
                new_status = DEFAULT_STATUS
                dispose_value = YES
            elif folded == LEGACY_HALTED.casefold():
                new_status = DEFAULT_STATUS
                dispose_value = NO
            else:
                new_status = old_status or DEFAULT_STATUS
                dispose_value = NO

            if new_status.casefold() in protected:
                dispose_value = NO

            values['status'] = new_status
            values[DISPOSE_KEY] = dispose_value
            sample.custom_values = values
            sample.status = new_status
            if dispose_value == YES and sample.automatic_disposal_started_at is None:
                sample.automatic_disposal_started_at = sample.modified_at or sample.created_at
            sample.save(update_fields=['custom_values', 'status', 'automatic_disposal_started_at'])


def backwards(apps, schema_editor):
    # Data cannot be losslessly reconstructed after custom statuses are edited.
    # Keep row data intact if this migration is reversed; schema state still rolls back.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0048_customer_requested_information_action'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name='problemsample',
            name='status',
            field=models.CharField(blank=True, db_index=True, default=DEFAULT_STATUS, max_length=80),
        ),
        migrations.AlterField(
            model_name='problemtable',
            name='pt_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Automatic-disposal expiration period in days from the most recent change of Dispose Automatically from No to Yes. Zero means immediate eligibility when automatic disposal is enabled.',
                validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(3650)],
            ),
        ),
    ]
