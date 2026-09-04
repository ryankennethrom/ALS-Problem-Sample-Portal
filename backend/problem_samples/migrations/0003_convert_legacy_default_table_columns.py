import uuid
from django.db import migrations


LEGACY_COLUMNS = [
    ('Problem ID', 'problem-id', 'text', True),
    ('Lab', 'lab', 'text', True),
    ('Status', 'status', 'text', True),
    ('ALS Sample Tracking Number', 'als-sample-tracking-number', 'text', True),
    ('Number of problem samples in shipment', 'number-of-problem-samples-in-shipment', 'number', False),
    ('Brand', 'brand', 'text', True),
    ('Distributor', 'distributor', 'text', True),
    ('End User', 'end-user', 'text', True),
    ('Date Received', 'date-received', 'date', True),
    ('Problem Type', 'problem-type', 'text', True),
    ('Issue description', 'issue-description', 'long_text', True),
    ('Created By', 'created-by', 'text', True),
    ('Client Contact Email', 'client-contact-email', 'email', True),
    ('Courier', 'courier', 'text', True),
    ('Courier Tracking', 'courier-tracking', 'text', True),
    ('Modified By', 'modified-by', 'text', True),
    ('Notify', 'notify', 'boolean', False),
    ('Email Confirmation', 'email-confirmation', 'boolean', False),
]


def convert_default_table(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    table = ProblemTable.objects.filter(is_default=True).first()
    if not table:
        return

    # Only seed the legacy/default table when it has no user-defined schema yet.
    # New tables still start with zero columns.
    if ProblemColumn.objects.filter(table_id=table.id).exists():
        return

    for position, (name, field_key, column_type, searchable) in enumerate(LEGACY_COLUMNS, start=1):
        ProblemColumn.objects.create(
            id=uuid.uuid4(),
            table_id=table.id,
            name=name,
            field_key=field_key,
            column_type=column_type,
            required=False,
            searchable=searchable,
            choices=[],
            default_value=None,
            position=position,
        )

    for problem in ProblemSample.objects.filter(table_id=table.id).iterator():
        values = dict(problem.custom_values or {})
        mapping = {
            'problem-id': problem.source_id or '',
            'lab': problem.lab or '',
            'status': problem.status or '',
            'als-sample-tracking-number': problem.als_tracking_number or '',
            'number-of-problem-samples-in-shipment': problem.problem_sample_count,
            'brand': problem.brand or '',
            'distributor': problem.distributor or '',
            'end-user': problem.end_user or '',
            'date-received': problem.date_received.isoformat() if problem.date_received else '',
            'problem-type': problem.problem_type or '',
            'issue-description': problem.issue_description or '',
            'created-by': problem.legacy_created_by or '',
            'client-contact-email': problem.client_contact_email or '',
            'courier': problem.courier or '',
            'courier-tracking': problem.courier_tracking_number or '',
            'modified-by': problem.legacy_modified_by or '',
            'notify': bool(problem.notify),
            'email-confirmation': bool(problem.email_confirmation),
        }
        values.update(mapping)
        ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0002_dynamic_problem_tables'),
    ]

    operations = [
        migrations.RunPython(convert_default_table, migrations.RunPython.noop),
    ]
