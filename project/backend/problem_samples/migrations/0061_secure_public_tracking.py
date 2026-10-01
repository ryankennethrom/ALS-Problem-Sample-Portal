import re
import secrets

from django.db import migrations, models


STRONG_TOKEN = re.compile(r'^[A-Za-z0-9_-]{64}$')


def rotate_legacy_tokens(apps, schema_editor):
    Sample = apps.get_model('problem_samples', 'ProblemSample')
    Prepared = apps.get_model('problem_samples', 'PreparedProblemSample')
    History = apps.get_model('problem_samples', 'ProblemHistory')
    database = schema_editor.connection.alias
    for sample in Sample.objects.using(database).exclude(acknowledgement_token__isnull=True).iterator():
        old = sample.acknowledgement_token
        if not old or STRONG_TOKEN.fullmatch(old):
            continue
        new = secrets.token_urlsafe(48)
        sample.acknowledgement_token = new
        values = dict(sample.custom_values or {})
        current_link = values.get('system-tracking-link')
        fields = ['acknowledgement_token']
        if isinstance(current_link, str) and f'/track/{old}' in current_link:
            values['system-tracking-link'] = current_link.replace(f'/track/{old}', f'/track/{new}')
            sample.custom_values = values
            fields.append('custom_values')
        sample.save(update_fields=fields)
        if sample.customer_notified_at:
            History.objects.using(database).create(
                problem_id=sample.pk, action='updated', actor=None,
                summary='Legacy tracking link rotated; resend the customer email',
                details={'security_rotation': True, 'changes': []},
            )
    for prepared in Prepared.objects.using(database).filter(completed_problem__isnull=True).iterator():
        if not STRONG_TOKEN.fullmatch(prepared.tracking_token or ''):
            prepared.tracking_token = secrets.token_urlsafe(48)
            prepared.save(update_fields=['tracking_token'])


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0060_notification_recipient')]

    operations = [
        migrations.AddField(
            model_name='problemsample', name='pending_tracking_token',
            field=models.CharField(blank=True, default=None, editable=False, max_length=128, null=True),
        ),
        migrations.CreateModel(
            name='PublicTrackingRateBucket',
            fields=[
                ('key', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('count', models.PositiveIntegerField(default=0)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.RunPython(rotate_legacy_tokens, migrations.RunPython.noop),
    ]
