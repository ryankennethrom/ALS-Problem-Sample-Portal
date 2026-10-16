from django.db import migrations


def make_issue_description_optional(apps, schema_editor):
    """Relax existing Issue Description column definitions without changing ticket data.

    The legacy ProblemSample.issue_description model field already accepts blanks.
    Ticket-level validation is controlled by ProblemColumn.required, which may have
    been enabled by administrators in one or more tables.
    """
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    columns = ProblemColumn.objects.filter(required=True).only('id', 'name', 'field_key')
    ids = [
        column.id for column in columns.iterator()
        if column.field_key == 'issue-description'
        or ''.join(ch for ch in column.name.lower() if ch.isalnum()) == 'issuedescription'
    ]
    if ids:
        ProblemColumn.objects.filter(id__in=ids).update(required=False)


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0080_take_back_samples_label')]

    operations = [
        migrations.RunPython(make_issue_description_optional, migrations.RunPython.noop),
    ]
