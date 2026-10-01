from datetime import timedelta
from django.db import migrations, models

POST_ACK_STATUSES = {
    'Problem acknowledged by customer',
    'To be Disposed',
    'Disposed',
    'Shipped back to client',
}


def seed_status_change_anchor(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemTable.objects.update(acknowledgement_link_days=30)
    for sample in ProblemSample.objects.all().iterator():
        values = sample.custom_values or {}
        current = str(values.get('status') or sample.status or '').strip()
        if current not in POST_ACK_STATUSES:
            sample.acknowledgement_status_changed_at = None
            sample.acknowledged_at = None
            sample.customer_acknowledgement_action = ''
            sample.save(update_fields=['acknowledgement_status_changed_at', 'acknowledged_at', 'customer_acknowledgement_action'])
            continue
        anchor = sample.acknowledged_at if current == 'Problem acknowledged by customer' and sample.acknowledged_at else sample.modified_at
        sample.acknowledgement_status_changed_at = anchor
        sample.save(update_fields=['acknowledgement_status_changed_at'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0029_customer_acknowledgement_action'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemsample',
            name='acknowledgement_status_changed_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(seed_status_change_anchor, migrations.RunPython.noop),
    ]
