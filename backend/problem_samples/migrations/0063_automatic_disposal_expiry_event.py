from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def backfill_automatic_disposal_expiry_events(apps, schema_editor):
    ProblemHistory = apps.get_model('problem_samples', 'ProblemHistory')
    AutomaticDisposalExpiryEvent = apps.get_model('problem_samples', 'AutomaticDisposalExpiryEvent')
    database = schema_editor.connection.alias

    histories = (
        ProblemHistory.objects.using(database)
        .filter(summary='Automatic disposal period ended')
        .order_by('created_at', 'id')
    )
    for history in histories.iterator():
        details = history.details or {}
        if details.get('automatic') is not True:
            continue
        effective_at = parse_datetime(str(details.get('effective_at') or '').strip())
        if effective_at is None:
            effective_at = history.created_at
        elif timezone.is_naive(effective_at):
            effective_at = timezone.make_aware(effective_at, timezone.get_current_timezone())
        AutomaticDisposalExpiryEvent.objects.using(database).get_or_create(
            ticket_id=history.problem_id,
            effective_at=effective_at,
        )


def clear_automatic_disposal_expiry_events(apps, schema_editor):
    AutomaticDisposalExpiryEvent = apps.get_model('problem_samples', 'AutomaticDisposalExpiryEvent')
    AutomaticDisposalExpiryEvent.objects.using(schema_editor.connection.alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0062_problem_tracking_link_table')]

    operations = [
        migrations.CreateModel(
            name='AutomaticDisposalExpiryEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('effective_at', models.DateTimeField(db_index=True)),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('ticket', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='automatic_disposal_expiry_events',
                    to='problem_samples.problemsample',
                )),
            ],
            options={
                'db_table': 'problem_samples_automatic_disposal_expiry_event',
                'ordering': ['effective_at', 'id'],
            },
        ),
        migrations.RunPython(
            backfill_automatic_disposal_expiry_events,
            clear_automatic_disposal_expiry_events,
        ),
        migrations.AddConstraint(
            model_name='automaticdisposalexpiryevent',
            constraint=models.UniqueConstraint(
                fields=('ticket', 'effective_at'),
                name='unique_auto_disposal_expiry_per_ticket_deadline',
            ),
        ),
    ]
