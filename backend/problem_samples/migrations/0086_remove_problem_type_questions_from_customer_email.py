"""Remove Problem Type chat instructions from the default tracking email.

Only the untouched built-in template is modified. Custom templates remain
unchanged; the email renderer substitutes an empty string for any legacy
{{problem_type_questions}} token.
"""
from django.db import migrations


OLD_DEFAULT_BODY = """To Whom It May Concern,

Thank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.

{{multiple_contacts_notice}}

Please review the following details regarding the affected sample(s) and the reason for the sample processing hold:
{{sample_initial_information}}

{{problem_type_questions}}

{{tracking_link}}

{{automatic_disposal_notice}}

We value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.

Should you have any questions or require further assistance, please do not hesitate to reach out.

Thank you for your prompt attention to this matter.

Regards,
ALS"""
NEW_DEFAULT_BODY = """To Whom It May Concern,

Thank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.

{{multiple_contacts_notice}}

Please review the following details regarding the affected sample(s) and the reason for the sample processing hold:
{{sample_initial_information}}

{{tracking_link}}

{{automatic_disposal_notice}}

We value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.

Should you have any questions or require further assistance, please do not hesitate to reach out.

Thank you for your prompt attention to this matter.

Regards,
ALS"""


def update_default_customer_email(apps, schema_editor):
    EmailTemplate = apps.get_model('problem_samples', 'EmailTemplate')
    EmailTemplate.objects.using(schema_editor.connection.alias).filter(
        key='customer_notification', body_template=OLD_DEFAULT_BODY,
    ).update(body_template=NEW_DEFAULT_BODY)


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0085_tracking_link_only')]
    operations = [migrations.RunPython(update_default_customer_email, migrations.RunPython.noop)]
