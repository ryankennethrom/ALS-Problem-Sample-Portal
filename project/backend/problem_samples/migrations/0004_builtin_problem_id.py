from django.db import migrations, models
import uuid


def seed_problem_ids(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    for table in ProblemTable.objects.all().iterator():
        column = ProblemColumn.objects.filter(table_id=table.id, field_key='problem-id').first()
        if column:
            column.name = 'Problem ID'
            column.column_type = 'number'
            column.required = True
            column.searchable = True
            column.choices = []
            column.default_value = None
            column.position = 0
            column.is_system = True
            column.save()
        else:
            ProblemColumn.objects.create(
                id=uuid.uuid4(), table_id=table.id, name='Problem ID', field_key='problem-id',
                column_type='number', required=True, searchable=True, choices=[],
                default_value=None, position=0, is_system=True,
            )

        used = set()
        next_number = 1
        for problem in ProblemSample.objects.filter(table_id=table.id).order_by('created_at', 'id').iterator():
            values = dict(problem.custom_values or {})
            raw = values.pop('problem-id', None)
            candidate = None
            try:
                parsed = int(str(raw).strip()) if raw not in (None, '') else None
                if parsed and parsed > 0 and parsed not in used:
                    candidate = parsed
            except (TypeError, ValueError):
                pass
            if candidate is None:
                while next_number in used:
                    next_number += 1
                candidate = next_number
            used.add(candidate)
            next_number = max(next_number, candidate + 1)
            problem.problem_number = candidate
            problem.custom_values = values
            problem.save(update_fields=['problem_number', 'custom_values'])

        table.next_problem_id = (max(used) + 1) if used else 1
        table.save(update_fields=['next_problem_id'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0003_convert_legacy_default_table_columns'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemtable',
            name='next_problem_id',
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='problemcolumn',
            name='is_system',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='problem_number',
            field=models.PositiveBigIntegerField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(seed_problem_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='problemsample',
            name='problem_number',
            field=models.PositiveBigIntegerField(db_index=True, editable=False),
        ),
        migrations.AddConstraint(
            model_name='problemsample',
            constraint=models.UniqueConstraint(fields=('table', 'problem_number'), name='unique_problem_number_per_table'),
        ),
    ]
