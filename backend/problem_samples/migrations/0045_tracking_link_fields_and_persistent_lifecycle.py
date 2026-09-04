from django.db import migrations
from django.db.models import F


TRACKING_STATUSES = {
    'To be Disposed',
    'Disposed',
    'To be shipped back to client',
    'Shipped back to client',
    'To be back to testing',
    'Back to testing',
}


def add_tracking_system_columns(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')

    for table in ProblemTable.objects.all().iterator():
        link = ProblemColumn.objects.filter(table=table, field_key='system-tracking-link').first()
        expiry = ProblemColumn.objects.filter(table=table, field_key='system-tracking-link-expiry').first()
        if link is None and expiry is None:
            ProblemColumn.objects.filter(table=table, position__gte=3).update(position=F('position') + 2)
        elif link is None:
            ProblemColumn.objects.filter(table=table, position__gte=3).exclude(pk=expiry.pk).update(position=F('position') + 1)
        elif expiry is None:
            ProblemColumn.objects.filter(table=table, position__gte=4).exclude(pk=link.pk).update(position=F('position') + 1)

        ProblemColumn.objects.update_or_create(
            table=table, field_key='system-tracking-link',
            defaults={
                'name': 'Tracking Link',
                'description': 'Persistent secure Problem Sample Tracking Link for this row. At most one link exists per problem sample.',
                'column_type': 'url', 'required': False, 'searchable': False,
                'include_in_customer_notification': False, 'choices': [], 'default_value': None,
                'position': 3, 'is_system': True,
            },
        )
        ProblemColumn.objects.update_or_create(
            table=table, field_key='system-tracking-link-expiry',
            defaults={
                'name': 'Tracking Link Expiry',
                'description': 'When the tracking link becomes inaccessible. It resets to 30 days whenever Status switches to a disposal, shipping, or back-to-testing workflow state.',
                'column_type': 'datetime', 'required': False, 'searchable': False,
                'include_in_customer_notification': False, 'choices': [], 'default_value': None,
                'position': 4, 'is_system': True,
            },
        )

    # Rebuild the expiry anchor from the latest known Status transition into one
    # of the six qualifying states. Older releases also used this database field
    # for customer acknowledgement/Halted, so keeping those old timestamps would
    # incorrectly expire links under the new rules.
    ProblemHistory = apps.get_model('problem_samples', 'ProblemHistory')
    for sample in ProblemSample.objects.all().iterator():
        latest_anchor = None
        histories = ProblemHistory.objects.filter(problem_id=sample.pk).order_by('-created_at', '-id')
        for history in histories.iterator():
            details = history.details or {}
            for change in details.get('changes', []) or []:
                if str(change.get('field') or '').strip().lower() != 'status':
                    continue
                after = str(change.get('after') or '').strip()
                if after in TRACKING_STATUSES:
                    latest_anchor = history.created_at
                    break
            if latest_anchor is not None:
                break

        values = sample.custom_values or {}
        current_status = str(values.get('status') or sample.status or '').strip()
        if latest_anchor is None and current_status in TRACKING_STATUSES:
            # Legacy/imported rows may have no structured history entry. Existing
            # lifecycle metadata is the best anchor; modified_at is a safe fallback.
            latest_anchor = sample.acknowledgement_status_changed_at or sample.modified_at

        if sample.acknowledgement_status_changed_at != latest_anchor:
            sample.acknowledgement_status_changed_at = latest_anchor
            sample.save(update_fields=['acknowledgement_status_changed_at'])


def remove_tracking_system_columns(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key__in=[
        'system-tracking-link', 'system-tracking-link-expiry'
    ]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0044_remove_customer_access_code_hold_sample'),
    ]

    operations = [
        migrations.RunPython(add_tracking_system_columns, remove_tracking_system_columns),
    ]
