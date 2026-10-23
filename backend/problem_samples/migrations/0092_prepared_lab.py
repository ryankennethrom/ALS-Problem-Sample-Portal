from django.db import migrations, models
import django.db.models.deletion


def backfill(apps, schema_editor):
    db=schema_editor.connection.alias
    lab=apps.get_model('accounts','Lab').objects.using(db).get(code='EDM')
    apps.get_model('problem_samples','PreparedProblemSample').objects.using(db).filter(lab__isnull=True).update(lab=lab)

class Migration(migrations.Migration):
    dependencies=[('problem_samples','0091_timing_lab')]
    operations=[migrations.AddField(model_name='preparedproblemsample',name='lab',field=models.ForeignKey(
        null=True,blank=True,on_delete=django.db.models.deletion.PROTECT,related_name='prepared_tickets',to='accounts.lab')),
        migrations.RunPython(backfill,migrations.RunPython.noop)]
