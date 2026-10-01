from datetime import timedelta

from django.db import migrations, models
import django.db.models.deletion


TRACKING_LINK_DAYS = 30


def move_tracking_links(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemTrackingLink = apps.get_model('problem_samples', 'ProblemTrackingLink')
    database = schema_editor.connection.alias

    for sample in ProblemSample.objects.using(database).exclude(acknowledgement_token__isnull=True).iterator():
        token = str(sample.acknowledgement_token or '').strip()
        if not token:
            continue
        expires_at = None
        if sample.acknowledgement_status_changed_at:
            expires_at = sample.acknowledgement_status_changed_at + timedelta(days=TRACKING_LINK_DAYS)
        link = ProblemTrackingLink.objects.using(database).create(
            ticket_id=sample.pk,
            tracking_token=token,
            expires_at=expires_at,
        )
        created_at = sample.customer_notified_at or sample.created_at
        if created_at:
            ProblemTrackingLink.objects.using(database).filter(pk=link.pk).update(date_created=created_at)


def restore_tracking_links(apps, schema_editor):
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemTrackingLink = apps.get_model('problem_samples', 'ProblemTrackingLink')
    database = schema_editor.connection.alias

    for link in ProblemTrackingLink.objects.using(database).all().iterator():
        ProblemSample.objects.using(database).filter(pk=link.ticket_id).update(
            acknowledgement_token=link.tracking_token,
        )


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0061_secure_public_tracking')]

    operations = [
        migrations.CreateModel(
            name='ProblemTrackingLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tracking_token', models.CharField(max_length=128, unique=True)),
                ('expires_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('ticket', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='tracking_link_record', to='problem_samples.problemsample')),
            ],
            options={'db_table': 'problem_samples_tracking_link'},
        ),
        migrations.RunPython(move_tracking_links, restore_tracking_links),
        migrations.RemoveField(
            model_name='problemsample',
            name='acknowledgement_token',
        ),
    ]
