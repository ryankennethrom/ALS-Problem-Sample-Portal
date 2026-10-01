from django.db import migrations


def rename_builtin_column(apps, schema_editor):
    column = apps.get_model('problem_samples', 'ProblemColumn')
    column.objects.filter(field_key='problem-id', name='Problem ID').update(name='Ticket ID')


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0056_prepared_problem_sample')]
    operations = [migrations.RunPython(rename_builtin_column, migrations.RunPython.noop)]
