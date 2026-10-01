import re
import secrets
import string
import unicodedata

from django.contrib.auth.models import User
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

ALS_EMAIL_SUFFIX = '@alsglobal.com'


def normalize_als_email(value: str) -> str:
    email = str(value or '').strip().lower()
    if not email:
        raise ValueError('ALS email is required.')
    try:
        validate_email(email)
    except ValidationError as exc:
        raise ValueError('Enter a valid ALS email address.') from exc
    if not email.endswith(ALS_EMAIL_SUFFIX) or email == ALS_EMAIL_SUFFIX:
        raise ValueError(f'Email must use the {ALS_EMAIL_SUFFIX} domain.')
    return email


def user_has_als_email(user) -> bool:
    try:
        normalize_als_email(getattr(user, 'email', ''))
        return True
    except ValueError:
        return False


def _username_component(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    ascii_value = normalized.encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+', '', ascii_value)


def derive_unique_username(first_name: str, last_name: str) -> str:
    first = _username_component(first_name)
    last = _username_component(last_name)
    if not first or not last:
        raise ValueError('First Name and Last Name must each contain at least one letter or number.')

    base = f'{first}.{last}'[:140]
    candidate = base
    suffix = 2
    while User.objects.filter(username__iexact=candidate).exists():
        suffix_text = str(suffix)
        candidate = f'{base[:150-len(suffix_text)]}{suffix_text}'
        suffix += 1
    return candidate


def generate_temporary_password(length: int = 20) -> str:
    if length < 12:
        raise ValueError('Temporary passwords must be at least 12 characters long.')

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = '!@#$%'
    all_chars = lower + upper + digits + symbols

    chars = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    chars.extend(secrets.choice(all_chars) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)
