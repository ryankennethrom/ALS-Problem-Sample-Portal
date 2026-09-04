from django.db import migrations
from django.db.models import F


FIELD_KEY = 'system-days-until-automatic-disposal'


def forward(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')

    for table in ProblemTable.objects.all():
        column = ProblemColumn.objects.filter(table=table, field_key=FIELD_KEY).first()
        if column is None:
            ProblemColumn.objects.filter(table=table, position__gte=2).update(position=F('position') + 1)
            ProblemColumn.objects.create(
                table=table,
                name='Days until automatic disposal',
                description='Read-only countdown until this sample becomes automatically eligible for disposal. The countdown starts after the customer notification is confirmed sent and applies only while Status is Automatically Disposed.',
                field_key=FIELD_KEY,
                column_type='number',
                required=False,
                searchable=True,
                include_in_customer_notification=False,
                choices=[],
                default_value=None,
                position=2,
                is_system=True,
            )
        else:
            ProblemColumn.objects.filter(pk=column.pk).update(
                name='Days until automatic disposal',
                description='Read-only countdown until this sample becomes automatically eligible for disposal. The countdown starts after the customer notification is confirmed sent and applies only while Status is Automatically Disposed.',
                column_type='number',
                required=False,
                searchable=True,
                include_in_customer_notification=False,
                choices=[],
                default_value=None,
                position=2,
                is_system=True,
            )


def reverse(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    for table in ProblemTable.objects.all():
        ProblemColumn.objects.filter(table=table, field_key=FIELD_KEY).delete()
        ProblemColumn.objects.filter(table=table, position__gte=3).update(position=F('position') - 1)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0037_halted_automatic_disposal_default'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
