from .models import NotificationRecipient


EDMONTON_RECIPIENT_KEY = 'na_edm'
DEFAULT_EDMONTON_RECIPIENT = 'NAEDM.DE@ALSGlobal.com'


def get_edmonton_recipient():
    recipient, _ = NotificationRecipient.objects.get_or_create(
        key=EDMONTON_RECIPIENT_KEY, defaults={'email': DEFAULT_EDMONTON_RECIPIENT}
    )
    return recipient
