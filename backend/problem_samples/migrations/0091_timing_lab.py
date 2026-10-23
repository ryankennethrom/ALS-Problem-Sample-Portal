from django.db import migrations, models
import django.db.models.deletion


def backfill(apps, schema_editor):
    db=schema_editor.connection.alias
    Lab=apps.get_model('accounts','Lab')
    Timing=apps.get_model('problem_samples','TicketCreationTiming')
    edmonton=Lab.objects.using(db).get(code='EDM')
    for record in Timing.objects.using(db).select_related('completed_ticket').filter(lab__isnull=True).iterator():
        record.lab_id = getattr(record.completed_ticket, 'lab_id', None) or edmonton.pk
        record.save(update_fields=['lab'], using=db)

class Migration(migrations.Migration):
    dependencies=[('problem_samples','0090_system_email_lab')]
    operations=[migrations.AddField(model_name='ticketcreationtiming',name='lab',field=models.ForeignKey(
        null=True,blank=True,on_delete=django.db.models.deletion.PROTECT,related_name='ticket_creation_timings',to='accounts.lab')),
        migrations.RunPython(backfill,migrations.RunPython.noop)]
