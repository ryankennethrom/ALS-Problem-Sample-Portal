from django.db import migrations, models
import django.db.models.deletion


def mark_edmonton_data(apps, schema_editor):
    db = schema_editor.connection.alias
    Lab = apps.get_model('accounts', 'Lab')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemContainer = apps.get_model('problem_samples', 'ProblemContainer')
    NotificationRecipient = apps.get_model('problem_samples', 'NotificationRecipient')
    lab = Lab.objects.using(db).get(code='EDM')
    # Preserve the sender's existing configured NA.EDM recipient on upgrade.
    old_recipient = NotificationRecipient.objects.using(db).filter(key='na_edm').first()
    if old_recipient and old_recipient.email:
        lab.lab_notification_emails = [old_recipient.email]
    ProblemSample.objects.using(db).filter(lab__isnull=True).update(lab=lab)
    # Preserve the existing numeric identifier for all existing physical containers.
    for container in ProblemContainer.objects.using(db).filter(lab__isnull=True).iterator():
        container.lab_id = lab.pk
        container.lab_number = container.pk
        container.save(update_fields=['lab', 'lab_number'], using=db)
    top = (ProblemContainer.objects.using(db).filter(lab=lab)
           .order_by('-lab_number').values_list('lab_number', flat=True).first() or 0)
    lab.next_container_number = top + 1
    lab.save(update_fields=['next_container_number', 'lab_notification_emails'], using=db)
    for table in ProblemTable.objects.using(db).all().iterator():
        ProblemColumn.objects.using(db).get_or_create(table_id=table.id, field_key='system-lab', defaults={
            'name': 'Lab', 'column_type': 'lab', 'required': True, 'searchable': True,
            'position': 6, 'is_system': True,
        })


class Migration(migrations.Migration):
    dependencies = [('accounts', '0007_lab'), ('problem_samples', '0088_ticket_creation_timings')]
    operations = [
        migrations.AddField(model_name='problemcontainer', name='lab', field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='containers', to='accounts.lab', db_index=True)),
        migrations.AddField(model_name='problemcontainer', name='lab_number', field=models.PositiveBigIntegerField(blank=True, null=True)),
        migrations.AddField(model_name='problemsample', name='lab', field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='tickets', to='accounts.lab', db_index=True)),
        migrations.CreateModel(name='LabEmailTemplate', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('key', models.CharField(max_length=80)),
            ('subject_template', models.CharField(max_length=500)),
            ('body_template', models.TextField()),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('lab', models.ForeignKey(to='accounts.lab', on_delete=django.db.models.deletion.CASCADE, related_name='email_templates')),
            ('updated_by', models.ForeignKey(to='auth.user', null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL)),
        ]),
        migrations.AddConstraint(model_name='problemcontainer', constraint=models.UniqueConstraint(
            fields=('lab', 'lab_number'), name='unique_container_number_per_lab')),
        migrations.AddConstraint(model_name='labemailtemplate', constraint=models.UniqueConstraint(
            fields=('lab', 'key'), name='unique_lab_email_template')),
        migrations.RunPython(mark_edmonton_data, migrations.RunPython.noop),
    ]
