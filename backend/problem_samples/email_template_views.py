import re
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import UserProfile
from .email_templates import (
    ALLOWED_CUSTOMER_NOTIFICATION_PLACEHOLDERS,
    CUSTOMER_NOTIFICATION_KEY,
    CUSTOMER_NOTIFICATION_NAME,
    DEFAULT_CUSTOMER_NOTIFICATION_BODY,
    DEFAULT_CUSTOMER_NOTIFICATION_SUBJECT,
    REQUIRED_CUSTOMER_NOTIFICATION_PLACEHOLDERS,
)
from .models import EmailTemplate
from .notification_recipient import get_edmonton_recipient

PLACEHOLDER_RE = re.compile(r'{{\s*([a-zA-Z0-9_]+)\s*}}')


def _is_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return bool(profile.is_admin)


def _get_customer_template():
    template, _ = EmailTemplate.objects.get_or_create(
        key=CUSTOMER_NOTIFICATION_KEY,
        defaults={
            'name': CUSTOMER_NOTIFICATION_NAME,
            'subject_template': DEFAULT_CUSTOMER_NOTIFICATION_SUBJECT,
            'body_template': DEFAULT_CUSTOMER_NOTIFICATION_BODY,
        },
    )
    return template


def _payload(template):
    return {
        'key': template.key,
        'name': template.name,
        'subject_template': template.subject_template,
        'body_template': template.body_template,
        'allowed_placeholders': ALLOWED_CUSTOMER_NOTIFICATION_PLACEHOLDERS,
        'required_placeholders': REQUIRED_CUSTOMER_NOTIFICATION_PLACEHOLDERS,
        'default_subject_template': DEFAULT_CUSTOMER_NOTIFICATION_SUBJECT,
        'default_body_template': DEFAULT_CUSTOMER_NOTIFICATION_BODY,
        'updated_at': template.updated_at,
        'updated_by': (template.updated_by.get_full_name().strip() or template.updated_by.username) if template.updated_by else '',
    }


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def customer_notification_template(request):
    template = _get_customer_template()

    # Every authenticated staff user can read the active template because the
    # browser uses it to compose Outlook/mailto customer notifications. Only
    # administrators may modify it.
    if request.method == 'GET':
        return Response(_payload(template))

    if not _is_admin(request.user):
        return Response(
            {'detail': 'Administrator access is required.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    subject = str(request.data.get('subject_template') or '').strip()
    body = str(request.data.get('body_template') or '').strip()
    if not subject:
        return Response({'detail': 'Email subject cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(subject) > 500:
        return Response({'detail': 'Email subject must be 500 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)
    if not body:
        return Response({'detail': 'Email body cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(body) > 20000:
        return Response({'detail': 'Email body must be 20,000 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

    allowed = set(ALLOWED_CUSTOMER_NOTIFICATION_PLACEHOLDERS)
    used = set(PLACEHOLDER_RE.findall(subject)) | set(PLACEHOLDER_RE.findall(body))
    unknown = sorted(used - allowed)
    if unknown:
        return Response(
            {'detail': 'Unknown template placeholder(s): ' + ', '.join('{{' + value + '}}' for value in unknown)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    missing = [
        name for name in REQUIRED_CUSTOMER_NOTIFICATION_PLACEHOLDERS
        if not re.search(r'{{\s*' + re.escape(name) + r'\s*}}', body)
    ]
    if missing:
        return Response(
            {'detail': 'The email body must include: ' + ', '.join('{{' + value + '}}' for value in missing)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    template.subject_template = subject
    template.body_template = body
    template.updated_by = request.user
    template.save(update_fields=['subject_template', 'body_template', 'updated_by', 'updated_at'])
    return Response(_payload(template))


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def edmonton_recipient(request):
    if request.method == 'PUT':
        if not _is_admin(request.user):
            return Response({'detail': 'Administrator access is required.'}, status=status.HTTP_403_FORBIDDEN)
        email = request.data.get('email')
        if not isinstance(email, str) or not email.strip() or len(email.strip()) > 254:
            return Response({'email': 'Enter one valid email address.'}, status=status.HTTP_400_BAD_REQUEST)
        email = email.strip()
        try:
            validate_email(email)
        except DjangoValidationError:
            return Response({'email': 'Enter one valid email address.'}, status=status.HTTP_400_BAD_REQUEST)
        recipient = get_edmonton_recipient()
        recipient.email = email
        recipient.updated_by = request.user
        recipient.save(update_fields=['email', 'updated_by', 'updated_at'])
    else:
        recipient = get_edmonton_recipient()
    return Response({
        'email': recipient.email, 'updated_at': recipient.updated_at,
        'updated_by': (recipient.updated_by.get_full_name().strip() or recipient.updated_by.username) if recipient.updated_by else '',
    })
