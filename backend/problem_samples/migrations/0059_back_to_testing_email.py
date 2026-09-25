from django.db import migrations, models
from django.db.models import Q


OLD = 'To be back to testing'
NEW = 'Back to testing'
KEY = 'current-workflow'


def migrate_workflow(apps, schema_editor):
    Column = apps.get_model('problem_samples', 'ProblemColumn')
    Sample = apps.get_model('problem_samples', 'ProblemSample')
    for column in Column.objects.filter(field_key=KEY).iterator():
        choices = [choice for choice in (column.choices or []) if choice != OLD]
        if NEW not in choices:
            choices.append(NEW)
        column.choices = choices
        column.save(update_fields=['choices'])
    for sample in Sample.objects.filter(Q(current_workflow=OLD) | Q(**{'custom_values__current-workflow': OLD})).iterator():
        values = dict(sample.custom_values or {})
        if values.get(KEY) == OLD:
            values[KEY] = NEW
        sample.current_workflow = NEW
        sample.custom_values = values
        sample.save(update_fields=['current_workflow', 'custom_values'])


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0058_waiting_for_customer_workflow')]
    operations = [
        migrations.AddField(model_name='problemsample', name='back_to_testing_notified_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(migrate_workflow, migrations.RunPython.noop),
    ]
