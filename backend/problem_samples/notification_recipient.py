from .models import NotificationRecipient


EDMONTON_RECIPIENT_KEY = 'na_edm'
DEFAULT_EDMONTON_RECIPIENT = 'NAEDM.DE@ALSGlobal.com'


def get_edmonton_recipient():
    recipient, _ = NotificationRecipient.objects.get_or_create(
        key=EDMONTON_RECIPIENT_KEY, defaults={'email': DEFAULT_EDMONTON_RECIPIENT}
    )
    return recipient


def addresses_for_lab(lab, role):
    """Resolve per-lab role addresses for mail drafts and @mentions."""
    from accounts.models import UserProfile
    if lab is None:
        return []
    prefix = 'lab' if role == UserProfile.ROLE_LAB_TECHNICIAN else 'customer_service'
    mode = getattr(lab, f'{prefix}_notification_mode')
    if mode == 'addresses':
        return list(getattr(lab, f'{prefix}_notification_emails') or [])
    return list(UserProfile.objects.filter(
        lab=lab, role=role, user__is_active=True,
    ).exclude(user__email='').values_list('user__email', flat=True).distinct())
