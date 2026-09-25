CUSTOMER_NOTIFICATION_KEY = 'customer_notification'
CUSTOMER_NOTIFICATION_NAME = 'Ticket Customer Email'

DEFAULT_CUSTOMER_NOTIFICATION_SUBJECT = '{{problem_type}} / Ticket ID #{{problem_id}}'

DEFAULT_CUSTOMER_NOTIFICATION_BODY = """To Whom It May Concern,

Thank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.

{{multiple_contacts_notice}}

Please review the following details regarding the affected sample(s) and the reason for the sample processing hold:
{{problem_details}}

{{additional_information}}

Please review and update this ticket using the secure Ticket Tracking Link below, or contact our Customer Service team at {{na_edm_email}} for assistance:

TICKET TRACKING LINK

{{tracking_link}}

The Ticket Tracking page also shows the available ticket details, images, and files.

{{automatic_disposal_notice}}

We value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.

Should you have any questions or require further assistance, please do not hesitate to reach out.

Thank you for your prompt attention to this matter.

Regards,
ALS"""

ALLOWED_CUSTOMER_NOTIFICATION_PLACEHOLDERS = [
    'na_edm_email',
    'problem_id',
    'problem_type',
    'als_sample_tracking_number',
    'reason_for_hold',
    'date_received',
    'problem_details',
    'additional_information',
    'multiple_contacts_notice',
    'tracking_link',
    'automatic_disposal_notice',
]
REQUIRED_CUSTOMER_NOTIFICATION_PLACEHOLDERS = ['tracking_link']
