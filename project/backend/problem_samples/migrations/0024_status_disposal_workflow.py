import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


SYSTEM_STATUSES = [
    'Disposed',
    'To Be Disposed',
    'Waiting For Response',
    'In Progress',
]
CANONICAL = {value.casefold(): value for value in SYSTEM_STATUSES}


def canonical_status(value):
    text = str(value or '').strip()
    return CANONICAL.get(text.casefold(), text)


def seed_required_status_columns(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    for table in ProblemTable.objects.all().iterator():
        status_column = ProblemColumn.objects.filter(table_id=table.id, field_key='status').first()
        if status_column is None:
            status_column = ProblemColumn.objects.filter(table_id=table.id, name__iexact='Status').order_by('position', 'created_at').first()

        old_key = status_column.field_key if status_column else 'status'
        custom_labels = []
        seen = {value.casefold() for value in SYSTEM_STATUSES}

        if status_column:
            for raw in status_column.choices or []:
                value = canonical_status(raw)
                if value and value.casefold() not in seen:
                    custom_labels.append(value)
                    seen.add(value.casefold())

        for problem in ProblemSample.objects.filter(table_id=table.id).iterator():
            values = dict(problem.custom_values or {})
            raw = values.get(old_key)
            if raw in (None, '') and old_key != 'status':
                raw = values.get('status')
            if raw in (None, ''):
                raw = problem.status
            value = canonical_status(raw) or 'Waiting For Response'
            if value.casefold() not in seen:
                custom_labels.append(value)
                seen.add(value.casefold())
            values['status'] = value
            if old_key != 'status':
                values.pop(old_key, None)
            ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values, status=value)

        custom_statuses = [{'id': str(uuid.uuid4()), 'label': label} for label in custom_labels]
        ProblemTable.objects.filter(pk=table.pk).update(custom_statuses=custom_statuses)
        all_choices = SYSTEM_STATUSES + custom_labels

        if status_column:
            # If a Status-named user column used another key, move it to the reserved key.
            if old_key != 'status':
                conflict = ProblemColumn.objects.filter(table_id=table.id, field_key='status').exclude(pk=status_column.pk).first()
                if conflict:
                    # Extremely old/hand-edited schemas may contain both. Keep the reserved-key
                    # column as the Status column and leave the other one untouched.
                    status_column = conflict
            ProblemColumn.objects.filter(pk=status_column.pk).update(
                name='Status',
                field_key='status',
                column_type='choice',
                required=True,
                searchable=True,
                choices=all_choices,
                default_value='Waiting For Response',
                group_role='',
                client_email_dependencies=[],
                depends_on_column_id=None,
                position=1,
                is_system=True,
            )
        else:
            ProblemColumn.objects.create(
                id=uuid.uuid4(),
                table_id=table.id,
                name='Status',
                description='Current workflow status of the problem sample.',
                field_key='status',
                column_type='choice',
                required=True,
                searchable=True,
                include_in_customer_notification=False,
                choices=all_choices,
                default_value='Waiting For Response',
                group_role='',
                client_email_dependencies=[],
                position=1,
                is_system=True,
            )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('problem_samples', '0023_containers_pt_expiration'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemtable',
            name='custom_statuses',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='User-defined workflow statuses. Required system statuses are managed by the application.',
            ),
        ),
        migrations.AddField(
            model_name='problemcontainer',
            name='disposed_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='problemcontainer',
            name='disposed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='problem_containers_disposed',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(seed_required_status_columns, migrations.RunPython.noop),
    ]
