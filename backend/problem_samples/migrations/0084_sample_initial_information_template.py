"""Switch untouched tracking-email templates to the selected-field placeholder.

Never overwrite templates that admins customized.
"""
from django.db import migrations


OLD_DEFAULT_BODY = 'To Whom It May Concern,\n\nThank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.\n\n{{multiple_contacts_notice}}\n\nPlease review the following details regarding the affected sample(s) and the reason for the sample processing hold:\n{{problem_details}}\n\n{{additional_information}}\n\nPlease review and update this ticket using the secure Ticket Tracking Link below, or contact our Customer Service team at {{na_edm_email}} for assistance:\n\nTICKET TRACKING LINK\n\n{{tracking_link}}\n\nThe Ticket Tracking page also shows the available ticket details, images, and files.\n\n{{automatic_disposal_notice}}\n\nWe value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.\n\nShould you have any questions or require further assistance, please do not hesitate to reach out.\n\nThank you for your prompt attention to this matter.\n\nRegards,\nALS'
NEW_DEFAULT_BODY = OLD_DEFAULT_BODY.replace(
    '{{problem_details}}\n\n{{additional_information}}',
    '{{sample_initial_information}}\n\n{{problem_type_questions}}',
)


def update_untouched_customer_email(apps, schema_editor):
    EmailTemplate = apps.get_model('problem_samples', 'EmailTemplate')
    EmailTemplate.objects.using(schema_editor.connection.alias).filter(
        key='customer_notification', body_template=OLD_DEFAULT_BODY,
    ).update(body_template=NEW_DEFAULT_BODY)


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0083_system_emails')]
    operations = [migrations.RunPython(update_untouched_customer_email, migrations.RunPython.noop)]
