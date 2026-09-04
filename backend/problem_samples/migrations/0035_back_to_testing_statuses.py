from django.db import migrations


FIXED_STATUSES = [
    'Customer not yet contacted',
    'Customer emailed by system',
    'Problem acknowledged by customer',
    'To be Disposed',
    'To be shipped back to client',
    'To be back to testing',
    'Back to testing',
    'Disposed',
    'Shipped back to client',
]


def add_back_to_testing_statuses(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    for column in ProblemColumn.objects.filter(field_key='status'):
        column.choices = list(FIXED_STATUSES)
        column.save(update_fields=['choices'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0034_to_be_shipped_back_status'),
    ]

    operations = [
        migrations.RunPython(add_back_to_testing_statuses, migrations.RunPython.noop),
    ]
