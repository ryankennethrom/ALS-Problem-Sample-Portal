from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0100_monthly_report_portal')]
    operations = [
        migrations.AddField(
            model_name='problemcolumn', name='client_email_fallback_hours',
            field=models.PositiveIntegerField(null=True, blank=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(87600)],
                help_text='After this many hours without a new customer response, escalate to the next priority.'),
        ),
        migrations.AddField(model_name='problemsample', name='client_email_priority_state', field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name='problemsample', name='client_email_last_tracking_sent_at', field=models.DateTimeField(null=True, blank=True, db_index=True)),
        migrations.AddField(model_name='problemsample', name='client_email_last_customer_response_at', field=models.DateTimeField(null=True, blank=True)),
    ]
