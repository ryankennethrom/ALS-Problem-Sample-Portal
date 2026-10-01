from django.db import migrations, models


OLD_ACTION = 'neither'
NEW_ACTION = 'hold'
OLD_LABEL = 'Neither, right now, I will be contacting customer service'
NEW_LABEL = 'Hold sample'


def forwards(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemHistory = apps.get_model('problem_samples', 'ProblemHistory')

    ProblemSample.objects.filter(customer_acknowledgement_action=OLD_ACTION).update(
        customer_acknowledgement_action=NEW_ACTION
    )

    for history in ProblemHistory.objects.all().iterator():
        details = dict(history.details or {})
        changed = False
        if details.get('customer_action') == OLD_ACTION:
            details['customer_action'] = NEW_ACTION
            changed = True
        if details.get('customer_action_label') == OLD_LABEL:
            details['customer_action_label'] = NEW_LABEL
            changed = True

        summary = history.summary or ''
        new_summary = summary.replace(OLD_LABEL, NEW_LABEL)
        if new_summary != summary:
            history.summary = new_summary
            changed = True

        if changed:
            history.details = details
            history.save(update_fields=['summary', 'details'])


def backwards(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemHistory = apps.get_model('problem_samples', 'ProblemHistory')

    ProblemSample.objects.filter(customer_acknowledgement_action=NEW_ACTION).update(
        customer_acknowledgement_action=OLD_ACTION
    )

    for history in ProblemHistory.objects.all().iterator():
        details = dict(history.details or {})
        changed = False
        if details.get('customer_action') == NEW_ACTION:
            details['customer_action'] = OLD_ACTION
            changed = True
        if details.get('customer_action_label') == NEW_LABEL:
            details['customer_action_label'] = OLD_LABEL
            changed = True

        summary = history.summary or ''
        new_summary = summary.replace(NEW_LABEL, OLD_LABEL)
        if new_summary != summary:
            history.summary = new_summary
            changed = True

        if changed:
            history.details = details
            history.save(update_fields=['summary', 'details'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0043_secure_acknowledgement_token'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='problemsample',
            name='acknowledgement_code',
        ),
        migrations.AlterField(
            model_name='problemsample',
            name='customer_acknowledgement_action',
            field=models.CharField(
                blank=True,
                choices=[
                    ('dispose', 'Dispose Sample(s)'),
                    ('ship_back', 'Ship back samples'),
                    ('hold', 'Hold sample'),
                ],
                db_index=True,
                help_text='Optional follow-up action selected by the customer after acknowledging the problem sample notification.',
                max_length=20,
            ),
        ),
    ]
