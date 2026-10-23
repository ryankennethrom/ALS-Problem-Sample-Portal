from django.db import migrations, models
import django.db.models.deletion


def mark_existing(apps, schema_editor):
    db = schema_editor.connection.alias
    lab = apps.get_model('accounts', 'Lab').objects.using(db).get(code='EDM')
    apps.get_model('problem_samples', 'SystemEmail').objects.using(db).filter(lab__isnull=True).update(lab=lab)

class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0089_multi_lab')]
    operations = [
        migrations.AddField(model_name='systememail', name='lab', field=models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='system_emails', to='accounts.lab')),
        migrations.RemoveConstraint(model_name='systememail', name='unique_scheduled_monthly_email_per_rule_period'),
        migrations.AddConstraint(model_name='systememail', constraint=models.UniqueConstraint(
            fields=['lab', 'source_column', 'rule_identifier', 'period_start'],
            condition=models.Q(generation_mode='scheduled'), name='unique_scheduled_monthly_email_per_rule_period')),
        migrations.RunPython(mark_existing, migrations.RunPython.noop),
    ]
