from django.db import migrations


# Match the exact prior email body so administrator-edited templates keep their copy.
OLD_DEFAULT_BODY = 'To Whom It May Concern,\n\nThank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.\n\n{{multiple_contacts_notice}}\n\nPlease review the following details regarding the affected sample(s) and the reason for the sample processing hold:\n{{problem_details}}\n\n{{additional_information}}\n\nPlease review and update this problem sample using the secure Problem Sample Tracking Link below, or contact our Customer Service team at {{na_edm_email}} for assistance:\n\nPROBLEM SAMPLE TRACKING LINK\n\n{{tracking_link}}\n\nThe Problem Sample Tracking page also shows the available problem sample details, images, and files.\n\n{{automatic_disposal_notice}}\n\nWe value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.\n\nShould you have any questions or require further assistance, please do not hesitate to reach out.\n\nThank you for your prompt attention to this matter.\n\nRegards,\nALS'
NEW_DEFAULT_BODY = 'To Whom It May Concern,\n\nThank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.\n\n{{multiple_contacts_notice}}\n\nPlease review the following details regarding the affected sample(s) and the reason for the sample processing hold:\n{{problem_details}}\n\n{{additional_information}}\n\nPlease review and update this ticket using the secure Ticket Tracking Link below, or contact our Customer Service team at {{na_edm_email}} for assistance:\n\nTICKET TRACKING LINK\n\n{{tracking_link}}\n\nThe Ticket Tracking page also shows the available ticket details, images, and files.\n\n{{automatic_disposal_notice}}\n\nWe value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.\n\nShould you have any questions or require further assistance, please do not hesitate to reach out.\n\nThank you for your prompt attention to this matter.\n\nRegards,\nALS'


def rename_untouched_defaults(apps, schema_editor):
    db = schema_editor.connection.alias
    Table = apps.get_model('problem_samples', 'ProblemTable')
    Template = apps.get_model('problem_samples', 'EmailTemplate')

    original_tables = Table.objects.using(db).filter(is_default=True, name='Problem Samples')
    original_tables.filter(description='Default problem sample table').update(description='Default ticket table')
    original_tables.update(name='Tickets')

    templates = Template.objects.using(db).filter(key='customer_notification')
    templates.filter(name='Problem Sample Customer Email').update(name='Ticket Customer Email')
    templates.filter(body_template=OLD_DEFAULT_BODY).update(body_template=NEW_DEFAULT_BODY)


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0065_optional_container_testing_workflow')]
    operations = [migrations.RunPython(rename_untouched_defaults, migrations.RunPython.noop)]
