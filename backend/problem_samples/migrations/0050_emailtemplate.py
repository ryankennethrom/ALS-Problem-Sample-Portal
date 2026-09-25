from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_SUBJECT = '{{problem_type}} / Problem ID #{{problem_id}}'
DEFAULT_BODY = """To Whom It May Concern,

Thank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.

{{multiple_contacts_notice}}

Please review the following details regarding the affected sample(s) and the reason for the sample processing hold:
{{problem_details}}

{{additional_information}}

Please review and update this problem sample using the secure Problem Sample Tracking Link below, or contact our Customer Service team at naedm.de@alsglobal.com for assistance:

PROBLEM SAMPLE TRACKING LINK

{{tracking_link}}

The Problem Sample Tracking page also shows the available problem sample details, images, and files.

{{automatic_disposal_notice}}

We value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.

Should you have any questions or require further assistance, please do not hesitate to reach out.

Thank you for your prompt attention to this matter.

Regards,
ALS"""


def create_default_template(apps, schema_editor):
    EmailTemplate = apps.get_model('problem_samples', 'EmailTemplate')
    EmailTemplate.objects.get_or_create(
        key='customer_notification',
        defaults={
            'name': 'Problem Sample Customer Email',
            'subject_template': DEFAULT_SUBJECT,
            'body_template': DEFAULT_BODY,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('problem_samples', '0049_dispose_automatically_and_custom_statuses'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=80, unique=True)),
                ('name', models.CharField(max_length=160)),
                ('subject_template', models.CharField(max_length=500)),
                ('body_template', models.TextField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='email_templates_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name', 'key']},
        ),
        migrations.RunPython(create_default_template, migrations.RunPython.noop),
    ]
