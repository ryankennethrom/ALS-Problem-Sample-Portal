from django.db import migrations


def make_lab_optional(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')

    # Migration 0005 temporarily added Lab to every table. Keep it on the
    # legacy/default table, where the imported schema already included Lab,
    # but remove that automatically-added column from other tables.
    default_table = ProblemTable.objects.filter(is_default=True).first()
    qs = ProblemColumn.objects.filter(field_key='lab', is_system=True)
    if default_table:
        qs = qs.exclude(table_id=default_table.id)
    qs.delete()


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0005_fixed_edmonton_lab'),
    ]

    operations = [
        migrations.RunPython(make_lab_optional, migrations.RunPython.noop),
    ]
