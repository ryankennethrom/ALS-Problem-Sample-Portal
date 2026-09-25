from django.db import migrations


WORKFLOW = 'Waiting For Customer'


def add_workflow_to_existing_tables(apps, schema_editor):
    column_model = apps.get_model('problem_samples', 'ProblemColumn')
    for column in column_model.objects.filter(field_key='current-workflow').iterator():
        choices = list(column.choices or [])
        if WORKFLOW not in choices:
            index = choices.index('CS Follow-Up') + 1 if 'CS Follow-Up' in choices else 0
            choices.insert(index, WORKFLOW)
            column.choices = choices
            column.save(update_fields=['choices'])


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0057_rename_builtin_problem_id_to_ticket_id')]
    operations = [migrations.RunPython(add_workflow_to_existing_tables, migrations.RunPython.noop)]
