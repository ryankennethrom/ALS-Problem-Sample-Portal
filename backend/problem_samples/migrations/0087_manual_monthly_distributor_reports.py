from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0086_remove_problem_type_questions_from_customer_email')]

    operations = [
        migrations.AddField(
            model_name='systememail', name='generation_mode',
            field=models.CharField(default='scheduled', max_length=12),
        ),
        migrations.AddField(
            model_name='systememail', name='request_identifier',
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
        migrations.RemoveConstraint(
            model_name='systememail', name='unique_monthly_email_per_rule_period',
        ),
        migrations.AddConstraint(
            model_name='systememail',
            constraint=models.UniqueConstraint(
                fields=('source_column', 'rule_identifier', 'period_start'),
                condition=models.Q(generation_mode='scheduled'),
                name='unique_scheduled_monthly_email_per_rule_period',
            ),
        ),
    ]