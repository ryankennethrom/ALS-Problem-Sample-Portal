from django.db import migrations, models
import uuid


def make_lab_fixed(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    for table in ProblemTable.objects.all().iterator():
        column = ProblemColumn.objects.filter(table_id=table.id, field_key='lab').first()
        if column:
            column.name = 'Lab'
            column.column_type = 'text'
            column.required = True
            column.searchable = True
            column.choices = []
            column.default_value = 'Edmonton'
            column.position = 1
            column.is_system = True
            column.save()
        else:
            ProblemColumn.objects.create(
                id=uuid.uuid4(), table_id=table.id, name='Lab', field_key='lab',
                column_type='text', required=True, searchable=True, choices=[],
                default_value='Edmonton', position=1, is_system=True,
            )

        for problem in ProblemSample.objects.filter(table_id=table.id).only('id', 'custom_values').iterator():
            values = dict(problem.custom_values or {})
            values.pop('lab', None)
            ProblemSample.objects.filter(pk=problem.pk).update(lab='Edmonton', custom_values=values)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0004_builtin_problem_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='lab',
            field=models.CharField(db_index=True, default='Edmonton', editable=False, max_length=150),
        ),
        migrations.RunPython(make_lab_fixed, migrations.RunPython.noop),
    ]
