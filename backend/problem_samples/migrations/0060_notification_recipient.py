from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def update_existing_email_copy(apps, schema_editor):
    Template = apps.get_model('problem_samples', 'EmailTemplate')
    for template in Template.objects.filter(key='customer_notification'):
        updated = template.body_template.replace('naedm.de@alsglobal.com', '{{na_edm_email}}')
        if updated != template.body_template:
            template.body_template = updated
            template.save(update_fields=['body_template'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0059_back_to_testing_email'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationRecipient',
            fields=[
                ('key', models.CharField(max_length=80, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notification_recipients_updated', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(update_existing_email_copy, migrations.RunPython.noop),
    ]
