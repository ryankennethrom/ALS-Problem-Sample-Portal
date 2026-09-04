from django.db import migrations


FIXED_STATUSES = [
    'Customer not yet contacted',
    'Customer emailed by system',
    'Problem acknowledged by customer',
    'To be Disposed',
    'To be shipped back to client',
    'Disposed',
    'Shipped back to client',
]


def add_pending_ship_back_status(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    for column in ProblemColumn.objects.filter(field_key='status'):
        column.choices = list(FIXED_STATUSES)
        column.save(update_fields=['choices'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0033_acknowledgement_credentials_on_sent_confirmation'),
    ]

    operations = [
        migrations.RunPython(add_pending_ship_back_status, migrations.RunPython.noop),
    ]
