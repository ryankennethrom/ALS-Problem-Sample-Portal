import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_rule_identifiers(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    for column in ProblemColumn.objects.filter(column_type='distributor').iterator():
        rules = column.distributor_cc_rules or []
        changed = False
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if not rule.get('id'):
                rule['id'] = str(uuid.uuid4())
                changed = True
            if 'send_monthly_reports' not in rule:
                rule['send_monthly_reports'] = False
                changed = True
        if changed:
            column.distributor_cc_rules = rules
            column.save(update_fields=['distributor_cc_rules'])


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0082_distributor_cc_rules'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='SystemEmail',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('email_type', models.CharField(max_length=40, default='distributor_monthly')),
                ('rule_identifier', models.UUIDField()),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('distributor_pattern', models.CharField(max_length=160)),
                ('to_emails', models.JSONField(default=list)),
                ('subject', models.CharField(max_length=255)),
                ('body', models.TextField()),
                ('matched_ticket_count', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(max_length=12, default='pending', db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(null=True, blank=True)),
                ('source_column', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='system_emails', to='problem_samples.problemcolumn')),
                ('sent_by', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='confirmed_system_emails', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-period_start', '-created_at']},
        ),
        migrations.AddConstraint(model_name='systememail', constraint=models.UniqueConstraint(fields=['source_column', 'rule_identifier', 'period_start'], name='unique_monthly_email_per_rule_period')),
        migrations.RunPython(backfill_rule_identifiers, migrations.RunPython.noop),
    ]
