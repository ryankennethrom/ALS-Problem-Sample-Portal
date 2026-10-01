from datetime import timedelta
import hashlib
import uuid
from django.db import transaction
from django.db.models import Q, F
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core import signing
from django.core.files.base import ContentFile
from django.core.validators import validate_email
from django.http import HttpResponse, FileResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from email.message import EmailMessage
from email import policy
import mimetypes
import os
import re
from PIL import Image as PillowImage, UnidentifiedImageError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError
from accounts.models import UserProfile
from accounts.account_utils import normalize_als_email, user_has_als_email
from .models import ProblemSample, ProblemTrackingLink, PreparedProblemSample, ProblemComment, ProblemMention, ProblemImage, ProblemAttachment, ProblemTable, ProblemColumn, ProblemHistory, ProblemContainer, SYSTEM_PROBLEM_STATUSES, TERMINAL_PROBLEM_STATUSES, CURRENT_WORKFLOW_CHOICES, CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER, PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_TO_BE_SHIPPED_BACK, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING, PROBLEM_STATUS_BACK_TO_TESTING, PROBLEM_STATUS_SHIPPED_BACK, CUSTOMER_ACTION_DISPOSE, CUSTOMER_ACTION_SHIP_BACK, CUSTOMER_ACTION_HOLD, CUSTOMER_ACTION_REQUESTED_INFORMATION, generate_acknowledgement_token, is_strong_tracking_token, SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY, DISPOSE_AUTOMATICALLY_YES, DISPOSE_AUTOMATICALLY_NO, DISPOSE_AUTOMATICALLY_CHOICES, SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY, SYSTEM_TRACKING_LINK_FIELD_KEY, SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY
from .permissions import IsTrackerAdminOrReadOnly
from .notification_recipient import get_edmonton_recipient
from .serializers import (
    ProblemSampleSerializer, ShippingProblemSampleSerializer, CommentSerializer, ImageSerializer, AttachmentSerializer, ProblemTableSerializer, ProblemColumnSerializer, ProblemContainerSerializer,
)
from .search import search_problem_samples
from .advanced_search import advanced_search_problem_samples
from .image_processing import compress_problem_image


MAX_ROW_FILE_BYTES = 25 * 1024 * 1024
MAX_NOTIFICATION_FILES_BYTES = 20 * 1024 * 1024
MAX_CUSTOMER_RESPONSE_FILES = 12
MAX_CUSTOMER_RESPONSE_BYTES = 50 * 1024 * 1024


def _confirmed_testing_recipient(request):
    configured = get_edmonton_recipient().email
    supplied = request.data.get('email_recipient')
    if not isinstance(supplied, str) or supplied.strip().casefold() != configured.casefold():
        raise DRFValidationError({'email_recipient': 'The NA.EDM address has changed. Reopen the email preview before confirming.'})
    return configured
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP'}
MENTION_RE = re.compile(r'(?<![A-Za-z0-9_@])@([A-Za-z0-9_](?:[A-Za-z0-9_.+-]*[A-Za-z0-9_])?)', re.IGNORECASE)
MENTION_EMAIL_SUFFIX = '@alsglobal.com'
MENTION_GROUP_LAB = 'lab'
MENTION_GROUP_CUSTOMER_SERVICE = 'customerservice'
LAB_GROUP_EMAIL = 'NA.EDM@alsglobal.com'


def _mention_handle(user_or_username):
    """Return the short staff handle shown/typed in @mentions."""
    username = getattr(user_or_username, 'username', user_or_username) or ''
    username = str(username).strip()
    if username.lower().endswith(MENTION_EMAIL_SUFFIX):
        return username[:-len(MENTION_EMAIL_SUFFIX)]
    return username


def _extract_mention_handles(body):
    handles = []
    seen = set()
    for match in MENTION_RE.finditer(body or ''):
        handle = match.group(1).strip().lower()
        if handle and handle not in seen:
            seen.add(handle)
            handles.append(handle)
    return handles


def _lookup_mention_user(handle):
    user = User.objects.filter(username__iexact=handle, is_active=True).first()
    if user is None:
        user = User.objects.filter(
            username__iexact=f'{handle}{MENTION_EMAIL_SUFFIX}',
            is_active=True,
        ).first()
    return user


def _eligible_role_users(role):
    profiles = (
        UserProfile.objects.filter(role=role, user__is_active=True)
        .select_related('user')
        .order_by('user__first_name', 'user__last_name', 'user__username')
    )
    return [profile.user for profile in profiles if user_has_als_email(profile.user)]


def _resolve_mentions(body):
    """Resolve individual and role-group mentions.

    Returns (users, unavailable_direct_users, groups, direct_user_ids). Group
    mentions deliberately exclude staff who do not yet have a valid ALS email,
    because email-less staff cannot be mentioned.
    """
    resolved_by_id = {}
    unavailable = []
    groups = []
    direct_user_ids = set()

    for handle in _extract_mention_handles(body):
        if handle == MENTION_GROUP_LAB:
            if MENTION_GROUP_LAB not in groups:
                groups.append(MENTION_GROUP_LAB)
            for user in _eligible_role_users(UserProfile.ROLE_LAB_TECHNICIAN):
                resolved_by_id[user.id] = user
            continue
        if handle == MENTION_GROUP_CUSTOMER_SERVICE:
            if MENTION_GROUP_CUSTOMER_SERVICE not in groups:
                groups.append(MENTION_GROUP_CUSTOMER_SERVICE)
            for user in _eligible_role_users(UserProfile.ROLE_CUSTOMER_SERVICE):
                resolved_by_id[user.id] = user
            continue

        user = _lookup_mention_user(handle)
        if user is None:
            continue
        if not user_has_als_email(user):
            unavailable.append(user)
            continue
        resolved_by_id[user.id] = user
        direct_user_ids.add(user.id)

    return list(resolved_by_id.values()), unavailable, groups, direct_user_ids


def _mentioned_users_from_body(body):
    return _resolve_mentions(body)[0]


def _mention_delivery_addresses(users, groups, direct_user_ids):
    """Return one deduplicated To list for the single outbound mention email."""
    addresses = []
    seen = set()

    def add(address):
        raw = str(address or '').strip()
        key = raw.casefold()
        if raw and key not in seen:
            seen.add(key)
            addresses.append(raw)

    # @Lab is intentionally routed through the shared Edmonton mailbox rather
    # than sending one copy to every Lab staff address.
    if MENTION_GROUP_LAB in groups:
        add(LAB_GROUP_EMAIL)

    # @CustomerService is one email addressed to all eligible Customer Service
    # staff members' stored ALS addresses.
    if MENTION_GROUP_CUSTOMER_SERVICE in groups:
        for user in users:
            profile = getattr(user, 'tracker_profile', None)
            if profile and profile.role == UserProfile.ROLE_CUSTOMER_SERVICE:
                add(normalize_als_email(user.email))

    # Explicit individual mentions are also included in that same email.
    for user in users:
        if user.id in direct_user_ids:
            add(normalize_als_email(user.email))

    return addresses


def _mention_labels(users, groups, direct_user_ids):
    labels = []
    if MENTION_GROUP_LAB in groups:
        labels.append('@Lab')
    if MENTION_GROUP_CUSTOMER_SERVICE in groups:
        labels.append('@CustomerService')
    labels.extend(f'@{_mention_handle(user)}' for user in users if user.id in direct_user_ids)
    return labels


def _mention_notified_email(user, groups, direct_user_ids):
    # If the person was explicitly named, record their own address as the
    # delivery path even when they were also part of a group mention.
    if user.id in direct_user_ids:
        return normalize_als_email(user.email)
    profile = getattr(user, 'tracker_profile', None)
    if MENTION_GROUP_LAB in groups and profile and profile.role == UserProfile.ROLE_LAB_TECHNICIAN:
        return LAB_GROUP_EMAIL
    return normalize_als_email(user.email)


def _mention_email(problem, mentioned_by, users, groups, direct_user_ids, body):
    frontend = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    direct_url = f'{frontend}/problems/{problem.id}#follow-ups' if frontend else f'/problems/{problem.id}#follow-ups'
    author_name = mentioned_by.get_full_name().strip() or _mention_handle(mentioned_by)
    table_name = problem.table.name if problem.table_id else 'Tickets'
    recipients = _mention_delivery_addresses(users, groups, direct_user_ids)
    labels = _mention_labels(users, groups, direct_user_ids)
    subject = f'Mention on Ticket #{problem.problem_number}'
    message = (
        f'Hello,\n\n'
        f'{author_name} mentioned {", ".join(labels)} on Ticket #{problem.problem_number} in {table_name}.\n\n'
        f'Message:\n{(body or "").strip()}\n\n'
        f'Open the ticket directly:\n{direct_url}\n\n'
        'Regards,\nALS Edmonton Ticket Tracker'
    )
    return {
        # email is retained as a display/backward-compatibility field. New UI
        # uses recipients so every address is supplied to the mail client.
        'email': ', '.join(recipients),
        'recipients': recipients,
        'mentions': labels,
        'subject': subject,
        'body': message,
        'direct_url': direct_url,
    }


def _mention_confirmation_payload(problem, author, body, users, groups, direct_user_ids):
    return {
        'problem_id': str(problem.id),
        'author_id': author.id,
        'body_sha256': hashlib.sha256((body or '').encode('utf-8')).hexdigest(),
        'mentioned_users': [
            {'user_id': user.id, 'email': normalize_als_email(user.email)}
            for user in sorted(users, key=lambda item: item.id)
        ],
        'groups': sorted(groups),
        'direct_user_ids': sorted(direct_user_ids),
        'delivery_emails': [
            address.casefold()
            for address in _mention_delivery_addresses(users, groups, direct_user_ids)
        ],
    }


def _mention_user_payload(user):
    profile = getattr(user, 'tracker_profile', None)
    role_label = profile.get_role_display() if profile and profile.role else ''
    handle = _mention_handle(user)
    return {
        'id': user.id,
        'username': handle,
        'name': user.get_full_name().strip() or handle,
        'role_label': role_label,
        'kind': 'user',
    }


def _mention_group_payloads(query=''):
    query = str(query or '').strip().lower()
    groups = [
        {
            'id': 'group:lab',
            'username': 'Lab',
            'name': 'Lab',
            'role_label': f'All Lab users · email {LAB_GROUP_EMAIL}',
            'kind': 'group',
        },
        {
            'id': 'group:customer-service',
            'username': 'CustomerService',
            'name': 'Customer Service',
            'role_label': 'All Customer Service users with ALS email',
            'kind': 'group',
        },
    ]
    if not query:
        return groups
    return [entry for entry in groups if query in entry['username'].lower() or query in entry['name'].lower()]

def _change_reason(request):
    """Return an optional staff-supplied change reason.

    The UI always offers a reason modal, but staff may explicitly skip it.
    Keep the server-side length check so direct API clients cannot persist an
    oversized reason.
    """
    reason = str(
        request.headers.get('X-Change-Reason')
        or (request.data.get('change_reason') if hasattr(request, 'data') else '')
        or ''
    ).strip()
    if len(reason) > 1000:
        raise DRFValidationError({'detail': 'The change reason must be 1000 characters or fewer.'})
    return reason


def _history_details(details, reason=''):
    result = dict(details or {})
    if reason:
        result['reason'] = reason
    return result


def _required_email_not_sent_reason(value, field='reason'):
    if not isinstance(value, str) or not value.strip():
        raise DRFValidationError({field: 'Provide a reason why the email was not sent.'})
    reason = value.strip()
    if len(reason) > 500:
        raise DRFValidationError({field: 'The reason must be 500 characters or fewer.'})
    return reason


def _validate_uploaded_file(uploaded, *, image=False):
    if not uploaded:
        return 'Choose a file to upload.'
    if uploaded.size <= 0:
        return 'The selected file is empty.'
    if uploaded.size > MAX_ROW_FILE_BYTES:
        return 'Files must be 25 MB or smaller.'
    if image:
        try:
            picture = PillowImage.open(uploaded)
            image_format = (picture.format or '').upper()
            picture.verify()
            uploaded.seek(0)
        except (UnidentifiedImageError, OSError, ValueError):
            return 'The selected file is not a valid image.'
        if image_format not in ALLOWED_IMAGE_FORMATS:
            return 'Images must be JPEG, PNG, GIF, or WebP.'
    return ''



def _request_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off', ''}


def _validated_email_list(value):
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        address = str(item or '').strip()
        key = address.lower()
        if not address or key in seen:
            continue
        try:
            validate_email(address)
        except DjangoValidationError:
            continue
        seen.add(key)
        result.append(address)
    return result


def _add_message_file(message, field, filename, content_type=''):
    try:
        field.open('rb')
        data = field.read()
    finally:
        try:
            field.close()
        except Exception:
            pass
    guessed = content_type or mimetypes.guess_type(filename or '')[0] or 'application/octet-stream'
    if '/' not in guessed:
        guessed = 'application/octet-stream'
    maintype, subtype = guessed.split('/', 1)
    message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename or 'attachment')


def _history_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, dict)):
        return value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _automatic_disposal_history_value(problem):
    """Human-readable value for the built-in disposal countdown in History."""
    if not problem.dispose_automatically:
        return 'Unknown'
    days = problem.days_until_automatic_disposal
    if days is None:
        return '—'
    if days <= 0:
        return 'Eligible now'
    return f"{days} day{'s' if days != 1 else ''}"


def ensure_problem_id_column(table):
    column = table.columns.filter(field_key='problem-id').first()
    if column:
        changed = []
        desired = {
            'name': 'Ticket ID', 'column_type': ProblemColumn.TYPE_NUMBER, 'required': True,
            'searchable': True, 'choices': [], 'default_value': None, 'position': 0, 'is_system': True,
        }
        for field, value in desired.items():
            if getattr(column, field) != value:
                setattr(column, field, value); changed.append(field)
        if changed:
            column.save(update_fields=changed + ['modified_at'])
        return column
    return ProblemColumn.objects.create(
        table=table, name='Ticket ID', field_key='problem-id',
        column_type=ProblemColumn.TYPE_NUMBER, required=True, searchable=True,
        choices=[], default_value=None, position=0, is_system=True,
    )



def ensure_current_workflow_column(table):
    column = table.columns.filter(field_key=SYSTEM_CURRENT_WORKFLOW_FIELD_KEY).first()
    if column is None:
        # Insert immediately after Ticket ID. All later columns move right.
        table.columns.filter(position__gte=1).update(position=F('position') + 1)
        column = ProblemColumn.objects.create(
            table=table, name='Current Workflow',
            description='Required built-in routing state used by CS Follow-Up, disposal, shipping, back-to-testing, customer tracking, and automatic disposal.',
            field_key=SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE, required=True, searchable=True,
            include_in_customer_notification=False, choices=list(CURRENT_WORKFLOW_CHOICES),
            default_value=CURRENT_WORKFLOW_DEFAULT, position=1, is_system=True,
        )
    else:
        desired = {
            'name': 'Current Workflow',
            'description': 'Required built-in routing state used by CS Follow-Up, disposal, shipping, back-to-testing, customer tracking, and automatic disposal.',
            'column_type': ProblemColumn.TYPE_CHOICE, 'required': True, 'searchable': True,
            'include_in_customer_notification': False, 'choices': list(CURRENT_WORKFLOW_CHOICES),
            'default_value': CURRENT_WORKFLOW_DEFAULT, 'position': 1, 'is_system': True,
        }
        changed = []
        for field, value in desired.items():
            if getattr(column, field) != value:
                setattr(column, field, value); changed.append(field)
        if changed:
            column.save(update_fields=changed + ['modified_at'])
    return column

def ensure_dispose_automatically_column(table):
    column = table.columns.filter(field_key=SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY).first()
    if column is None:
        # Insert immediately after Current Workflow. All later built-in/custom columns move right.
        table.columns.filter(position__gte=2).update(position=F('position') + 1)
        column = ProblemColumn.objects.create(
            table=table, name='Dispose Automatically',
            description='Required built-in setting that controls whether the automatic-disposal countdown is active for this ticket.',
            field_key=SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE, required=True, searchable=True,
            include_in_customer_notification=False, choices=list(DISPOSE_AUTOMATICALLY_CHOICES),
            default_value=DISPOSE_AUTOMATICALLY_NO, position=2, is_system=True,
        )
    else:
        desired = {
            'name': 'Dispose Automatically',
            'description': 'Required built-in setting that controls whether the automatic-disposal countdown is active for this ticket.',
            'column_type': ProblemColumn.TYPE_CHOICE, 'required': True, 'searchable': True,
            'include_in_customer_notification': False, 'choices': list(DISPOSE_AUTOMATICALLY_CHOICES),
            'default_value': DISPOSE_AUTOMATICALLY_NO, 'position': 2, 'is_system': True,
        }
        changed = []
        for field, value in desired.items():
            if getattr(column, field) != value:
                setattr(column, field, value); changed.append(field)
        if changed:
            column.save(update_fields=changed + ['modified_at'])
    return column


def ensure_days_until_automatic_disposal_column(table):
    column = table.columns.filter(field_key=SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY).first()
    if column is None:
        table.columns.filter(position__gte=3).update(position=F('position') + 1)
        column = ProblemColumn.objects.create(
            table=table,
            name='Days until up for disposal',
            description='Read-only countdown until this sample automatically changes Current Workflow to To be Disposed. The countdown restarts whenever Dispose Automatically changes from No to Yes and is inactive while the value is No.',
            field_key=SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY,
            column_type=ProblemColumn.TYPE_NUMBER,
            required=False, searchable=True,
            include_in_customer_notification=False, choices=[], default_value=None,
            position=3, is_system=True,
        )
    else:
        desired = {
            'name': 'Days until up for disposal',
            'description': 'Read-only countdown until this sample automatically changes Current Workflow to To be Disposed. The countdown restarts whenever Dispose Automatically changes from No to Yes and is inactive while the value is No.',
            'column_type': ProblemColumn.TYPE_NUMBER, 'required': False, 'searchable': True,
            'include_in_customer_notification': False, 'choices': [], 'default_value': None,
            'position': 3, 'is_system': True,
        }
        changed = []
        for field, value in desired.items():
            if getattr(column, field) != value:
                setattr(column, field, value); changed.append(field)
        if changed:
            column.save(update_fields=changed + ['modified_at'])
    return column


def ensure_tracking_link_columns(table):
    link_column = table.columns.filter(field_key=SYSTEM_TRACKING_LINK_FIELD_KEY).first()
    expiry_column = table.columns.filter(field_key=SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY).first()

    # Positions 0..3 are Ticket ID, Current Workflow, Dispose Automatically, and Days until up for disposal.
    # Shift ordinary columns only when one or both tracking columns are missing.
    if link_column is None and expiry_column is None:
        table.columns.filter(position__gte=4).update(position=F('position') + 2)
    elif link_column is None:
        table.columns.filter(position__gte=4).exclude(pk=expiry_column.pk).update(position=F('position') + 1)
    elif expiry_column is None:
        table.columns.filter(position__gte=5).exclude(pk=link_column.pk).update(position=F('position') + 1)

    if link_column is None:
        link_column = ProblemColumn.objects.create(
            table=table, name='Tracking Link',
            description='Persistent secure Ticket Tracking Link for this row. At most one link exists per ticket.',
            field_key=SYSTEM_TRACKING_LINK_FIELD_KEY, column_type=ProblemColumn.TYPE_URL,
            required=False, searchable=False, include_in_customer_notification=False,
            choices=[], default_value=None, position=4, is_system=True,
        )
    else:
        desired = {
            'name': 'Tracking Link',
            'description': 'Persistent secure Ticket Tracking Link for this row. At most one link exists per ticket.',
            'column_type': ProblemColumn.TYPE_URL, 'required': False, 'searchable': False,
            'include_in_customer_notification': False, 'choices': [], 'default_value': None,
            'position': 4, 'is_system': True,
        }
        changed = []
        for field, value in desired.items():
            if getattr(link_column, field) != value:
                setattr(link_column, field, value); changed.append(field)
        if changed:
            link_column.save(update_fields=changed + ['modified_at'])

    if expiry_column is None:
        expiry_column = ProblemColumn.objects.create(
            table=table, name='Tracking Link Expiry',
            description='When the tracking link becomes inaccessible. It resets to 30 days whenever Current Workflow switches to a disposal, shipping, or back-to-testing state.',
            field_key=SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY, column_type=ProblemColumn.TYPE_DATETIME,
            required=False, searchable=False, include_in_customer_notification=False,
            choices=[], default_value=None, position=5, is_system=True,
        )
    else:
        desired = {
            'name': 'Tracking Link Expiry',
            'description': 'When the tracking link becomes inaccessible. It resets to 30 days whenever Current Workflow switches to a disposal, shipping, or back-to-testing state.',
            'column_type': ProblemColumn.TYPE_DATETIME, 'required': False, 'searchable': False,
            'include_in_customer_notification': False, 'choices': [], 'default_value': None,
            'position': 5, 'is_system': True,
        }
        changed = []
        for field, value in desired.items():
            if getattr(expiry_column, field) != value:
                setattr(expiry_column, field, value); changed.append(field)
        if changed:
            expiry_column.save(update_fields=changed + ['modified_at'])

    return link_column, expiry_column


def ensure_builtin_columns(table):
    ensure_problem_id_column(table)
    ensure_current_workflow_column(table)
    ensure_dispose_automatically_column(table)
    ensure_days_until_automatic_disposal_column(table)
    ensure_tracking_link_columns(table)


def get_default_table():
    table = ProblemTable.objects.filter(is_default=True).first()
    if table:
        ensure_builtin_columns(table)
        return table
    table = ProblemTable.objects.first()
    if table:
        ensure_builtin_columns(table)
        return table
    table = ProblemTable.objects.create(name='Tickets', description='Default ticket table', is_default=True)
    ensure_builtin_columns(table)
    return table


class ProblemSampleViewSet(viewsets.ModelViewSet):
    serializer_class = ProblemSampleSerializer

    def create(self, request, *args, **kwargs):
        # New tickets must go through the prepared tracking-email sequence. This
        # prevents API clients from creating a real ticket before staff explicitly
        # chooses either "I sent the email" or "I didn't send the email".
        return Response(
            {'detail': 'New tickets must be prepared through the tracking-link email step before they are created.'},
            status=status.HTTP_409_CONFLICT,
        )

    @action(detail=False, methods=['post'], url_path='prepare-new')
    def prepare_new(self, request):
        serializer = ProblemSampleSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        table = serializer.validated_data.get('table') or get_default_table()
        with transaction.atomic():
            table = ProblemTable.objects.select_for_update().get(pk=table.pk)
            ensure_builtin_columns(table)
            number = table.next_problem_id
            table.next_problem_id = number + 1
            table.save(update_fields=['next_problem_id', 'modified_at'])
            prepared = PreparedProblemSample.objects.create(
                table=table, created_by=request.user, problem_number=number,
                tracking_token=generate_acknowledgement_token(), payload=dict(request.data),
            )
        base = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        return Response({
            'id': str(prepared.pk), 'problem_number': number,
            'custom_values': serializer.validated_data.get('custom_values', {}),
            'tracking_url': f'{base}/track/{prepared.tracking_token}' if base else f'/track/{prepared.tracking_token}',
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='cancel-prepared')
    def cancel_prepared(self, request):
        try:
            prepared_id = uuid.UUID(str(request.data.get('id')))
        except (TypeError, ValueError, AttributeError):
            return Response({'detail': 'Choose a valid preparation.'}, status=status.HTTP_400_BAD_REQUEST)
        prepared = PreparedProblemSample.objects.filter(pk=prepared_id, created_by=request.user, completed_problem__isnull=True).first()
        if prepared:
            prepared.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='create-prepared')
    def create_prepared(self, request):
        try:
            prepared_id = uuid.UUID(str(request.data.get('id')))
        except (TypeError, ValueError, AttributeError):
            return Response({'detail': 'Prepare the customer information first.'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(request.data.get('sent'), bool):
            return Response({'detail': 'Confirm whether the email was sent.'}, status=status.HTTP_400_BAD_REQUEST)
        not_sent_reason = (_required_email_not_sent_reason(request.data.get('not_sent_reason'), 'not_sent_reason')
                           if request.data['sent'] is False else '')
        with transaction.atomic():
            prepared = PreparedProblemSample.objects.select_for_update().filter(pk=prepared_id, created_by=request.user).first()
            if not prepared:
                return Response({'detail': 'This preparation was cancelled or is no longer available.'}, status=status.HTTP_404_NOT_FOUND)
            if prepared.completed_problem_id:
                return Response({'id': str(prepared.completed_problem_id)})
            serializer = ProblemSampleSerializer(data=prepared.payload, context={'request': request})
            serializer.is_valid(raise_exception=True)
            problem = serializer.save(
                table=prepared.table, problem_number=prepared.problem_number,
                created_by=request.user, modified_by=request.user,
            )
            lifecycle_fields = problem.apply_acknowledgement_status_transition('', previous_dispose_automatically=False, changed_at=timezone.now())
            if lifecycle_fields:
                problem.save(update_fields=list(dict.fromkeys(lifecycle_fields)))
            ProblemHistory.objects.create(
                problem=problem, action=ProblemHistory.ACTION_CREATED, actor=request.user,
                summary='Created ticket', details={},
            )
            if not_sent_reason:
                ProblemHistory.objects.create(
                    problem=problem, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
                    summary='Customer tracking email not sent',
                    details={'email_not_sent': 'customer', 'reason': not_sent_reason, 'changes': []},
                )
            problem.transition_to_disposal_if_due(now=timezone.now())
            if request.data.get('sent') is True:
                recorded = self._record_customer_notification_sent(request, problem, prepared.tracking_token, 'mailto', prepared_token=prepared.tracking_token)
                if recorded.status_code >= 400:
                    raise DRFValidationError(recorded.data)
            else:
                # The user explicitly chose to create the ticket without sending the
                # email. Persist the prepared public credential anyway so the finalized
                # ticket has the same tracking link that was shown during the send step,
                # but do not mark the customer as notified or start automatic disposal.
                if not is_strong_tracking_token(prepared.tracking_token):
                    raise DRFValidationError({'detail': 'Invalid prepared ticket tracking token.'})
                if ProblemTrackingLink.objects.filter(tracking_token=prepared.tracking_token).exists():
                    raise DRFValidationError({'detail': 'The prepared ticket tracking link conflicts with another ticket. Prepare the ticket again.'})
                stored_link = ProblemTrackingLink.objects.create(
                    ticket=problem,
                    tracking_token=prepared.tracking_token,
                    expires_at=problem.expected_tracking_link_expiration(),
                )
                problem.tracking_link_record = stored_link
            prepared.completed_problem = problem
            prepared.save(update_fields=['completed_problem'])
        return Response({'id': str(problem.pk)}, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        queryset = (ProblemSample.objects.select_related('created_by', 'modified_by', 'table', 'container', 'tracking_link_record')
                    .prefetch_related('comments__mentions__mentioned_user', 'images__uploaded_by', 'attachments__uploaded_by', 'history__actor', 'table__columns')
                    .order_by('-problem_number'))
        table_id = self.request.query_params.get('table')
        if table_id:
            queryset = queryset.filter(table_id=table_id)

        # Dashboard "See samples" links carry an opened_range so the user
        # lands in the selected ticket table with the same date window that
        # produced the dashboard card count. Keep this filtering at queryset
        # level so normal search and advanced search continue to respect it.
        opened_range = str(self.request.query_params.get('opened_range') or '').strip().lower()
        if opened_range:
            from .dashboard_views import WINDOWS, _custom_bounds
            if opened_range in WINDOWS:
                queryset = queryset.filter(created_at__gte=timezone.now() - WINDOWS[opened_range])
            elif opened_range == 'custom':
                try:
                    _, _, start_at, end_at = _custom_bounds(
                        self.request.query_params.get('start_date'),
                        self.request.query_params.get('end_date'),
                    )
                except ValueError:
                    return queryset.none()
                queryset = queryset.filter(created_at__gte=start_at, created_at__lt=end_at)
        return queryset

    def perform_create(self, serializer):
        requested = serializer.validated_data.get('table') or get_default_table()
        with transaction.atomic():
            table = ProblemTable.objects.select_for_update().get(pk=requested.pk)
            ensure_builtin_columns(table)
            problem_number = table.next_problem_id
            table.next_problem_id = problem_number + 1
            table.save(update_fields=['next_problem_id', 'modified_at'])
            problem = serializer.save(
                table=table, problem_number=problem_number,
                created_by=self.request.user, modified_by=self.request.user,
            )
            lifecycle_fields = problem.apply_acknowledgement_status_transition('', previous_dispose_automatically=False, changed_at=timezone.now())
            if lifecycle_fields:
                problem.save(update_fields=list(dict.fromkeys(lifecycle_fields)))
            ProblemHistory.objects.create(
                problem=problem, action=ProblemHistory.ACTION_CREATED, actor=self.request.user,
                summary='Created ticket', details={},
            )
            # If this table uses a zero-day automatic-disposal period, persist
            # the To be Disposed transition in the same create request.
            problem.transition_to_disposal_if_due(now=timezone.now())

    @transaction.atomic
    def perform_update(self, serializer):
        reason = _change_reason(self.request)
        instance = serializer.instance
        before_custom = dict(instance.custom_values or {})
        before_core = {
            field: getattr(instance, field)
            for field in [
                'source_id', 'als_tracking_number', 'problem_sample_count', 'brand',
                'distributor', 'end_user', 'date_received', 'problem_type', 'issue_description',
                'client_contact_email', 'courier', 'courier_tracking_number', 'notify', 'email_confirmation',
            ]
        }
        before_status = str(before_custom.get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY) or instance.current_workflow or CURRENT_WORKFLOW_DEFAULT).strip()
        next_status = serializer.validated_data.get('current_workflow', before_status)
        sending_testing_email = False
        testing_email_not_sent_reason = ''
        testing_email_body = ''
        testing_email_recipient = ''
        if before_status != PROBLEM_STATUS_BACK_TO_TESTING and next_status == PROBLEM_STATUS_BACK_TO_TESTING:
            decision = self.request.data.get('back_to_testing_email_sent')
            if not isinstance(decision, bool):
                raise DRFValidationError({'back_to_testing_email_sent': 'Confirm whether the NA.EDM email was sent before changing the workflow.'})
            sending_testing_email = decision
            if not sending_testing_email:
                testing_email_not_sent_reason = _required_email_not_sent_reason(
                    self.request.data.get('back_to_testing_not_sent_reason'), 'back_to_testing_not_sent_reason'
                )
            testing_email_body = str(self.request.data.get('back_to_testing_email_body') or '').strip()
            if sending_testing_email and (not testing_email_body or len(testing_email_body) > 10000):
                raise DRFValidationError({'back_to_testing_email_body': 'Provide the email message (up to 10,000 characters).'})
            if sending_testing_email:
                testing_email_recipient = _confirmed_testing_recipient(self.request)
        before_auto = str(before_custom.get(SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY) or DISPOSE_AUTOMATICALLY_NO).strip().casefold() == DISPOSE_AUTOMATICALLY_YES.casefold()
        before_container = instance.container.container_id if instance.container_id and instance.container else ''
        problem = serializer.save(modified_by=self.request.user)
        lifecycle_fields = problem.apply_acknowledgement_status_transition(
            before_status, previous_dispose_automatically=before_auto
        )
        if lifecycle_fields:
            problem.save(update_fields=list(dict.fromkeys(lifecycle_fields)))
        if sending_testing_email and problem.workflow_status == PROBLEM_STATUS_BACK_TO_TESTING:
            problem.back_to_testing_notified_at = timezone.now()
            problem.save(update_fields=['back_to_testing_notified_at'])

        column_names = {c.field_key: c.name for c in problem.table.columns.all()} if problem.table else {}
        changes = []
        keys = sorted(set(before_custom) | set(problem.custom_values or {}))
        for key in keys:
            before = before_custom.get(key)
            after = (problem.custom_values or {}).get(key)
            if before != after:
                changes.append({
                    'field': column_names.get(key, key),
                    'before': _history_value(before),
                    'after': _history_value(after),
                })

        core_labels = {
            'source_id': 'Source ID', 'als_tracking_number': 'ALS Tracking Number',
            'problem_sample_count': 'Problem Sample Count', 'brand': 'Brand', 'distributor': 'Distributor',
            'end_user': 'End User', 'date_received': 'Date Received', 'problem_type': 'Problem Type',
            'issue_description': 'Issue Description', 'client_contact_email': 'Client Contact Email',
            'courier': 'Courier', 'courier_tracking_number': 'Courier Tracking Number',
            'notify': 'Notify', 'email_confirmation': 'Email Confirmation',
        }
        for field, before in before_core.items():
            after = getattr(problem, field)
            if before != after:
                changes.append({
                    'field': core_labels[field],
                    'before': _history_value(before),
                    'after': _history_value(after),
                })

        after_container = problem.container.container_id if problem.container_id and problem.container else ''
        if before_container != after_container:
            changes.append({
                'field': 'Container ID',
                'before': _history_value(before_container),
                'after': _history_value(after_container),
            })

        ProblemHistory.objects.create(
            problem=problem, action=ProblemHistory.ACTION_UPDATED, actor=self.request.user,
            summary='Saved changes', details=_history_details({'changes': changes}, reason),
        )
        if sending_testing_email and problem.workflow_status == PROBLEM_STATUS_BACK_TO_TESTING:
            ProblemHistory.objects.create(
                problem=problem, action=ProblemHistory.ACTION_UPDATED, actor=self.request.user,
                summary='Sent Back to Testing email to NA.EDM',
                details={'recipient': testing_email_recipient, 'email_body': testing_email_body, 'changes': []},
            )
        elif testing_email_not_sent_reason and problem.workflow_status == PROBLEM_STATUS_BACK_TO_TESTING:
            ProblemHistory.objects.create(
                problem=problem, action=ProblemHistory.ACTION_UPDATED, actor=self.request.user,
                summary='Back to Testing email not sent to NA.EDM',
                details={'email_not_sent': 'back_to_testing', 'reason': testing_email_not_sent_reason, 'changes': []},
            )
        # This mainly matters for PT = 0. Longer countdowns are transitioned by
        # request middleware as soon as a later request observes the due time.
        problem.transition_to_disposal_if_due(now=timezone.now())

    @action(detail=False, methods=['get', 'post'], url_path='follow-up-required')
    def follow_up_required(self, request):
        # CS Follow-Up is table-scoped.  The selected ProblemTable is the
        # source of truth for both searching and rendering; do not infer a table
        # from row values or from a collection of generic workflow fields.
        table_id = (request.data.get('table') if request.method.lower() == 'post' else request.query_params.get('table'))
        if not table_id:
            return Response({'detail': 'A ticket table is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            table = ProblemTable.objects.prefetch_related('columns').get(pk=table_id)
        except (ProblemTable.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Ticket table not found.'}, status=status.HTTP_404_NOT_FOUND)

        tracking_not_sent = str(
            request.data.get('tracking_not_sent') if request.method.lower() == 'post'
            else request.query_params.get('tracking_not_sent')
        ) == '1'
        other = str(
            request.data.get('other') if request.method.lower() == 'post'
            else request.query_params.get('other')
        ) == '1'
        if tracking_not_sent and other:
            return Response({'detail': 'Choose only one Customer Service queue.'}, status=status.HTTP_400_BAD_REQUEST)
        queryset = (ProblemSample.objects.select_related('created_by', 'modified_by', 'table', 'container', 'tracking_link_record')
                    .prefetch_related('table__columns')
                    .filter(table=table))
        if tracking_not_sent:
            from .dashboard_views import tracking_not_sent_tickets
            queryset = tracking_not_sent_tickets(queryset)
        elif other:
            from .dashboard_views import customer_service_other_tickets
            queryset = customer_service_other_tickets(queryset)

        if request.method.lower() == 'post':
            candidates = advanced_search_problem_samples(
                queryset,
                table,
                request.data.get('filters') or [],
                request.data.get('match') or 'all',
                request.data.get('q') or '',
                request.data.get('quick_filters') or [],
            )
        else:
            query = str(request.query_params.get('q') or '').strip()
            candidates = search_problem_samples(query, queryset) if query else list(queryset)

        # Keep active follow-up and waiting-for-customer tickets together,
        # then force oldest-first even when a search ranked by score.
        samples = [sample for sample in candidates if tracking_not_sent or other or sample.workflow_status in {CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER}]
        samples.sort(key=lambda sample: (sample.created_at, str(sample.id)))
        return Response(ShippingProblemSampleSerializer(samples, many=True, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='disposal-search')
    def disposal_search(self, request):
        query = str(request.query_params.get('q') or '').strip()
        if not query:
            return Response([])
        ranked = search_problem_samples(query, self.get_queryset())
        return Response(ShippingProblemSampleSerializer(ranked, many=True, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='disposal-browse')
    def disposal_browse(self, request):
        # Used when Dispose Samples has advanced-search conditions but no basic
        # search term. Advanced filtering is performed in the browser against
        # the same lightweight queue serializer used by the other workflow pages.
        queryset = self.get_queryset().order_by('-created_at', '-id')
        return Response(ShippingProblemSampleSerializer(queryset, many=True, context={'request': request}).data)

    @action(detail=False, methods=['post'], url_path='bulk-dispose')
    @transaction.atomic
    def bulk_dispose(self, request):
        reason = _change_reason(request)
        raw_ids = request.data.get('problem_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'detail': 'Select at least one ticket to dispose.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        problem_ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                problem_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return Response(
                    {'detail': f'Invalid ticket ID: {raw_id}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if problem_id not in seen:
                seen.add(problem_id)
                problem_ids.append(problem_id)

        samples = list(
            ProblemSample.objects.select_for_update()
            .prefetch_related('table__columns', 'container')
            .filter(pk__in=problem_ids)
        )
        by_id = {sample.id: sample for sample in samples}
        missing = [str(problem_id) for problem_id in problem_ids if problem_id not in by_id]
        if missing:
            return Response(
                {'detail': 'One or more selected tickets no longer exist.', 'missing_ids': missing},
                status=status.HTTP_404_NOT_FOUND,
            )

        ordered_samples = [by_id[problem_id] for problem_id in problem_ids]
        already_disposed = [sample for sample in ordered_samples if sample.workflow_status == PROBLEM_STATUS_DISPOSED]
        if already_disposed:
            return Response(
                {
                    'detail': 'One or more selected tickets are already Disposed. Refresh the search and try again.',
                    'blocking_problem_ids': [sample.problem_number for sample in already_disposed],
                },
                status=status.HTTP_409_CONFLICT,
            )

        disposed_container_samples = [
            sample for sample in ordered_samples
            if sample.container_id and sample.container and sample.container.disposed_at
        ]
        if disposed_container_samples:
            return Response(
                {
                    'detail': 'A selected ticket belongs to a disposed container. Undo that container disposal before disposing the sample individually.',
                    'blocking_problem_ids': [sample.problem_number for sample in disposed_container_samples],
                },
                status=status.HTTP_409_CONFLICT,
            )

        now = timezone.now()
        modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
        changed = []
        for sample in ordered_samples:
            before = sample.workflow_status
            before_auto = sample.dispose_automatically
            values = dict(sample.custom_values or {})
            values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_DISPOSED
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier

            sample.custom_values = values
            sample.current_workflow = PROBLEM_STATUS_DISPOSED
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(before, previous_dispose_automatically=before_auto, changed_at=now)
            sample.save(update_fields=list(dict.fromkeys([
                'custom_values', 'current_workflow', 'modified_by', 'modified_at', *lifecycle_fields,
            ])))
            ProblemHistory.objects.create(
                problem=sample,
                action=ProblemHistory.ACTION_UPDATED,
                actor=request.user,
                summary='Disposed sample',
                details=_history_details({
                    'disposal_action': 'bulk_dispose_samples',
                    'changes': [{
                        'field': 'Current Workflow',
                        'before': before,
                        'after': PROBLEM_STATUS_DISPOSED,
                    }],
                }, reason),
            )
            changed.append(sample)

        return Response({
            'count': len(changed),
            'problem_ids': [str(sample.id) for sample in changed],
            'problem_numbers': [sample.problem_number for sample in changed],
        })

    @action(detail=False, methods=['get'], url_path='to-be-shipped')
    def to_be_shipped(self, request):
        queryset = self.get_queryset().filter(
            Q(current_workflow=PROBLEM_STATUS_TO_BE_SHIPPED_BACK)
        )
        return Response(ShippingProblemSampleSerializer(queryset, many=True, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='back-to-testing')
    def back_to_testing(self, request):
        queryset = self.get_queryset().filter(current_workflow=PROBLEM_STATUS_BACK_TO_TESTING)
        return Response(ShippingProblemSampleSerializer(queryset, many=True, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='to-be-back-to-testing')
    def to_be_back_to_testing(self, request):
        queryset = self.get_queryset().filter(current_workflow=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        return Response(ShippingProblemSampleSerializer(queryset, many=True, context={'request': request}).data)

    @action(detail=False, methods=['post'], url_path='bulk-back-to-testing')
    @transaction.atomic
    def bulk_back_to_testing(self, request):
        reason = _change_reason(request)
        raw_ids = request.data.get('problem_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response({'detail': 'Select at least one ticket to return to testing.'}, status=status.HTTP_400_BAD_REQUEST)
        ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                problem_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return Response({'detail': f'Invalid ticket ID: {raw_id}'}, status=status.HTTP_400_BAD_REQUEST)
            if problem_id not in seen:
                seen.add(problem_id)
                ids.append(problem_id)

        samples = list(ProblemSample.objects.select_for_update().select_related('container', 'table')
                       .prefetch_related('table__columns').filter(pk__in=ids))
        by_id = {sample.id: sample for sample in samples}
        missing = [str(problem_id) for problem_id in ids if problem_id not in by_id]
        if missing:
            return Response({'detail': 'One or more selected tickets no longer exist.', 'missing_ids': missing}, status=status.HTTP_404_NOT_FOUND)
        ordered = [by_id[problem_id] for problem_id in ids]
        blocked = [sample for sample in ordered if sample.workflow_status != PROBLEM_STATUS_TO_BE_BACK_TO_TESTING]
        if blocked:
            return Response({
                'detail': 'One or more samples are no longer To be back to testing. Refresh the page and try again.',
                'blocking_problem_ids': [sample.problem_number for sample in blocked],
            }, status=status.HTTP_409_CONFLICT)
        disposed = [sample for sample in ordered if sample.container_id and sample.container and sample.container.disposed_at]
        if disposed:
            return Response({
                'detail': 'Undo container disposal before returning a sample in that container to testing.',
                'blocking_problem_ids': [sample.problem_number for sample in disposed],
            }, status=status.HTTP_409_CONFLICT)

        sent = request.data.get('back_to_testing_email_sent')
        if not isinstance(sent, bool):
            return Response({'back_to_testing_email_sent': 'Confirm whether the NA.EDM email was sent.'}, status=status.HTTP_400_BAD_REQUEST)
        body = str(request.data.get('back_to_testing_email_body') or '').strip()
        if sent:
            if not body or len(body) > 10000:
                return Response({'back_to_testing_email_body': 'Provide the email message (up to 10,000 characters).'}, status=status.HTTP_400_BAD_REQUEST)
            recipient = _confirmed_testing_recipient(request)
            not_sent_reason = ''
        else:
            recipient = ''
            not_sent_reason = _required_email_not_sent_reason(request.data.get('back_to_testing_not_sent_reason'), 'back_to_testing_not_sent_reason')

        now = timezone.now()
        modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
        for sample in ordered:
            previous_workflow = sample.workflow_status
            before_auto = sample.dispose_automatically
            previous_container = sample.container.container_id if sample.container_id and sample.container else ''
            values = dict(sample.custom_values or {})
            values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_BACK_TO_TESTING
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier
            sample.custom_values = values
            sample.current_workflow = PROBLEM_STATUS_BACK_TO_TESTING
            sample.container = None
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(
                previous_workflow, previous_dispose_automatically=before_auto, changed_at=now
            )
            if sent:
                sample.back_to_testing_notified_at = now
            sample.save(update_fields=list(dict.fromkeys([
                'custom_values', 'current_workflow', 'container', 'modified_by', 'modified_at',
                'back_to_testing_notified_at', *lifecycle_fields,
            ])))
            changes = [{'field': 'Current Workflow', 'before': previous_workflow, 'after': PROBLEM_STATUS_BACK_TO_TESTING}]
            if previous_container:
                changes.append({'field': 'Container ID', 'before': previous_container, 'after': '—'})
            ProblemHistory.objects.create(
                problem=sample, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
                summary='Moved back to testing',
                details=_history_details({'testing_action': 'bulk_back_to_testing', 'changes': changes}, reason),
            )
            ProblemHistory.objects.create(
                problem=sample, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
                summary='Sent Back to Testing email to NA.EDM' if sent else 'Back to Testing email not sent to NA.EDM',
                details=({'recipient': recipient, 'email_body': body, 'changes': []} if sent else
                         {'email_not_sent': 'back_to_testing', 'reason': not_sent_reason, 'changes': []}),
            )
        return Response({'count': len(ordered), 'problem_ids': [str(sample.id) for sample in ordered],
                         'problem_numbers': [sample.problem_number for sample in ordered]})

    @action(detail=True, methods=['post'], url_path='back-to-testing-notification')
    @transaction.atomic
    def back_to_testing_notification(self, request, pk=None):
        problem = ProblemSample.objects.select_for_update().get(pk=self.get_object().pk)
        if problem.workflow_status != PROBLEM_STATUS_BACK_TO_TESTING:
            return Response({'detail': 'This ticket is not Back to testing.'}, status=status.HTTP_409_CONFLICT)
        email_body = str(request.data.get('email_body') or '').strip()
        if not email_body or len(email_body) > 10000:
            return Response({'detail': 'Provide the email message (up to 10,000 characters).'}, status=status.HTTP_400_BAD_REQUEST)
        if problem.back_to_testing_notified_at is not None:
            return Response({'detail': 'NA.EDM has already been notified for this workflow change.'}, status=status.HTTP_409_CONFLICT)
        recipient = _confirmed_testing_recipient(request)
        problem.back_to_testing_notified_at = timezone.now()
        problem.save(update_fields=['back_to_testing_notified_at'])
        ProblemHistory.objects.create(
            problem=problem, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
            summary='Sent Back to Testing email to NA.EDM',
            details={'recipient': recipient, 'email_body': email_body, 'changes': []},
        )
        return Response({'notified_at': problem.back_to_testing_notified_at})

    @action(detail=True, methods=['post'], url_path='email-not-sent')
    def email_not_sent(self, request, pk=None):
        problem = self.get_object()
        kind = request.data.get('kind')
        if kind not in {'customer', 'back_to_testing'}:
            return Response({'detail': 'Choose the email that was not sent.'}, status=status.HTTP_400_BAD_REQUEST)
        reason = _required_email_not_sent_reason(request.data.get('reason'))
        if kind == 'back_to_testing' and (
            problem.workflow_status != PROBLEM_STATUS_BACK_TO_TESTING
            or problem.back_to_testing_notified_at is not None
        ):
            return Response({'detail': 'There is no outstanding Back to Testing email for this ticket.'}, status=status.HTTP_409_CONFLICT)
        ProblemHistory.objects.create(
            problem=problem, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
            summary=('Customer tracking email not sent' if kind == 'customer'
                     else 'Back to Testing email not sent to NA.EDM'),
            details={'email_not_sent': kind, 'reason': reason, 'changes': []},
        )
        return Response({'detail': 'Reason recorded.'}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='bulk-ship-back')
    @transaction.atomic
    def bulk_ship_back(self, request):
        reason = _change_reason(request)
        raw_ids = request.data.get('problem_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'detail': 'Select at least one ticket to ship.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        problem_ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                problem_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return Response(
                    {'detail': f'Invalid ticket ID: {raw_id}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if problem_id not in seen:
                seen.add(problem_id)
                problem_ids.append(problem_id)

        samples = list(
            ProblemSample.objects.select_for_update()
            .prefetch_related('table__columns', 'container')
            .filter(pk__in=problem_ids)
        )
        by_id = {sample.id: sample for sample in samples}
        missing = [str(problem_id) for problem_id in problem_ids if problem_id not in by_id]
        if missing:
            return Response(
                {'detail': 'One or more selected tickets no longer exist.', 'missing_ids': missing},
                status=status.HTTP_404_NOT_FOUND,
            )

        ordered_samples = [by_id[problem_id] for problem_id in problem_ids]
        blocked = [sample for sample in ordered_samples if sample.workflow_status != PROBLEM_STATUS_TO_BE_SHIPPED_BACK]
        if blocked:
            return Response(
                {
                    'detail': 'One or more selected tickets are no longer To be shipped back to client. Refresh the Shipping page and try again.',
                    'blocking_problem_ids': [sample.problem_number for sample in blocked],
                },
                status=status.HTTP_409_CONFLICT,
            )

        disposed_container_samples = [
            sample for sample in ordered_samples
            if sample.container_id and sample.container and sample.container.disposed_at
        ]
        if disposed_container_samples:
            return Response(
                {
                    'detail': 'A selected ticket belongs to a disposed container. Undo that container disposal before changing its shipping status.',
                    'blocking_problem_ids': [sample.problem_number for sample in disposed_container_samples],
                },
                status=status.HTTP_409_CONFLICT,
            )

        now = timezone.now()
        modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
        changed = []
        for sample in ordered_samples:
            before = sample.workflow_status
            before_auto = sample.dispose_automatically
            values = dict(sample.custom_values or {})
            values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_SHIPPED_BACK
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier

            sample.custom_values = values
            sample.current_workflow = PROBLEM_STATUS_SHIPPED_BACK
            previous_container = sample.container.container_id if sample.container_id and sample.container else ''
            sample.container = None
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(before, previous_dispose_automatically=before_auto, changed_at=now)
            sample.save(update_fields=list(dict.fromkeys([
                'custom_values', 'current_workflow', 'container', 'modified_by', 'modified_at', *lifecycle_fields,
            ])))
            ProblemHistory.objects.create(
                problem=sample,
                action=ProblemHistory.ACTION_UPDATED,
                actor=request.user,
                summary='Shipped back to client',
                details=_history_details({
                    'shipping_action': 'bulk_ship_back',
                    'changes': [{
                        'field': 'Current Workflow',
                        'before': before,
                        'after': PROBLEM_STATUS_SHIPPED_BACK,
                    }, *([{'field': 'Container ID', 'before': previous_container, 'after': '—'}] if previous_container else [])],
                }, reason),
            )
            changed.append(sample)

        return Response({
            'count': len(changed),
            'problem_ids': [str(sample.id) for sample in changed],
            'problem_numbers': [sample.problem_number for sample in changed],
        })

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        ranked = search_problem_samples(request.query_params.get('q', ''), self.get_queryset())
        return Response(self.get_serializer(ranked, many=True).data)

    @action(detail=False, methods=['post'], url_path='advanced-search')
    def advanced_search(self, request):
        table_id = request.data.get('table')
        if not table_id:
            return Response({'detail': 'A table is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            table = ProblemTable.objects.prefetch_related('columns').get(pk=table_id)
        except (ProblemTable.DoesNotExist, ValueError):
            return Response({'detail': 'Ticket table not found.'}, status=status.HTTP_404_NOT_FOUND)
        ranked = advanced_search_problem_samples(
            self.get_queryset(),
            table,
            request.data.get('filters') or [],
            request.data.get('match') or 'all',
            request.data.get('q') or '',
            request.data.get('quick_filters') or [],
        )
        return Response(self.get_serializer(ranked, many=True).data)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser], url_path='images')
    def upload_image(self, request, pk=None):
        problem = self.get_object()
        uploaded = request.FILES.get('file')
        error = _validate_uploaded_file(uploaded, image=True)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        original_name = (uploaded.name or 'image')[:255]
        try:
            compressed_bytes, stored_name = compress_problem_image(uploaded, original_name)
        except (UnidentifiedImageError, OSError, ValueError):
            return Response({'detail': 'The selected image could not be processed.'}, status=status.HTTP_400_BAD_REQUEST)
        if not compressed_bytes:
            return Response({'detail': 'The selected image could not be processed.'}, status=status.HTTP_400_BAD_REQUEST)

        image = ProblemImage.objects.create(
            problem=problem,
            image=ContentFile(compressed_bytes, name=stored_name),
            original_name=original_name,
            uploaded_by=request.user,
            include_in_customer_notification=_request_bool(request.data.get('include_in_customer_notification'), True),
        )
        return Response(ImageSerializer(image, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path=r'images/(?P<image_id>\d+)/content')
    def image_content(self, request, pk=None, image_id=None):
        """Stream a ticket image through the authenticated API.

        Staff frontends use bearer authentication, so production image previews
        cannot safely depend on Django's development-only /media/ serving.
        """
        problem = self.get_object()
        image = problem.images.filter(pk=image_id).first()
        if not image or not image.image:
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        stored_filename = os.path.basename(image.image.name) or f'image-{image.id}'
        filename = stored_filename if stored_filename.lower().endswith('.webp') else (image.original_name or stored_filename)
        content_type = mimetypes.guess_type(stored_filename)[0] or 'application/octet-stream'
        try:
            image.image.open('rb')
        except (OSError, ValueError):
            return Response({'detail': 'Image file is unavailable.'}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(image.image, as_attachment=False, filename=filename, content_type=content_type)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    @action(detail=True, methods=['delete', 'patch'], url_path=r'images/(?P<image_id>\d+)')
    def delete_image(self, request, pk=None, image_id=None):
        problem = self.get_object()
        try:
            image = problem.images.get(pk=image_id)
        except ProblemImage.DoesNotExist:
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        if request.method.lower() == 'patch':
            image.include_in_customer_notification = _request_bool(request.data.get('include_in_customer_notification'), image.include_in_customer_notification)
            image.save(update_fields=['include_in_customer_notification'])
            return Response(ImageSerializer(image, context={'request': request}).data)
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser], url_path='attachments')
    def upload_attachment(self, request, pk=None):
        problem = self.get_object()
        uploaded = request.FILES.get('file')
        error = _validate_uploaded_file(uploaded)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        attachment = ProblemAttachment.objects.create(
            problem=problem,
            file=uploaded,
            original_name=(uploaded.name or 'attachment')[:255],
            content_type=(getattr(uploaded, 'content_type', '') or '')[:160],
            size_bytes=uploaded.size,
            uploaded_by=request.user,
            include_in_customer_notification=_request_bool(request.data.get('include_in_customer_notification'), True),
        )
        return Response(AttachmentSerializer(attachment, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete', 'patch'], url_path=r'attachments/(?P<attachment_id>\d+)')
    def delete_attachment(self, request, pk=None, attachment_id=None):
        problem = self.get_object()
        try:
            attachment = problem.attachments.get(pk=attachment_id)
        except ProblemAttachment.DoesNotExist:
            return Response({'detail': 'Attachment not found.'}, status=status.HTTP_404_NOT_FOUND)
        if request.method.lower() == 'patch':
            attachment.include_in_customer_notification = _request_bool(request.data.get('include_in_customer_notification'), attachment.include_in_customer_notification)
            attachment.save(update_fields=['include_in_customer_notification'])
            return Response(AttachmentSerializer(attachment, context={'request': request}).data)
        attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='customer-notification-credentials')
    @transaction.atomic
    def customer_notification_credentials(self, request, pk=None):
        """Prepare a server-issued token without activating a public link."""
        problem = ProblemSample.objects.select_for_update().get(pk=self.get_object().pk)
        persisted = bool(problem.acknowledgement_token)
        if not persisted and not problem.pending_tracking_token:
            problem.pending_tracking_token = generate_acknowledgement_token()
            problem.save(update_fields=['pending_tracking_token'])
        token = problem.acknowledgement_token if persisted else problem.pending_tracking_token
        base = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        tracking_url = f'{base}/track/{token}' if base else f'/track/{token}'
        return Response({
            'tracking_token': str(token),
            'tracking_url': tracking_url,
            # Legacy aliases are kept temporarily for older frontend builds.
            'acknowledgement_token': str(token),
            'acknowledgement_url': tracking_url,
            'persisted': persisted,
        })

    @action(detail=True, methods=['post'], url_path='revoke-tracking-link')
    @transaction.atomic
    def revoke_tracking_link(self, request, pk=None):
        problem = ProblemSample.objects.select_for_update().get(pk=self.get_object().pk)
        link = problem.tracking_link_record_or_none
        if link is None:
            return Response({'detail': 'This ticket has no active tracking link to revoke.'}, status=status.HTTP_409_CONFLICT)
        reason = _change_reason(request)
        link.delete()
        if problem.pending_tracking_token:
            problem.pending_tracking_token = None
            problem.save(update_fields=['pending_tracking_token'])
        ProblemHistory.objects.create(
            problem=problem, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
            summary='Revoked tracking link',
            details=_history_details({'changes': [{'field': 'Tracking Link', 'before': 'Active', 'after': 'Revoked'}]}, reason),
        )
        return Response({'detail': 'Tracking link revoked. The old URL cannot be used again.'})

    @action(detail=True, methods=['post'], url_path='customer-message-sent')
    def customer_message_sent(self, request, pk=None):
        """Record ordinary correspondence without creating or changing a tracking link."""
        problem = self.get_object()
        recipients = _validated_email_list(request.data.get('to'))
        subject = str(request.data.get('subject') or '').strip()
        body = str(request.data.get('body') or '').strip()
        if not recipients:
            return Response({'detail': 'At least one valid customer email address is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not subject or len(subject) > 500 or not body or len(body) > 10000:
            return Response({'detail': 'Provide a subject (up to 500 characters) and a message (up to 10,000 characters).'}, status=status.HTTP_400_BAD_REQUEST)
        history = ProblemHistory.objects.create(
            problem=problem, action=ProblemHistory.ACTION_CUSTOMER_NOTIFICATION, actor=request.user,
            summary='Sent an email to the customer',
            details={'recipients': recipients, 'subject': subject, 'delivery_method': 'mailto',
                     'confirmation': 'Staff confirmed sending a general customer email.', 'changes': []},
        )
        return Response({'id': history.id, 'summary': history.summary}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='customer-notification-draft')
    def customer_notification_draft(self, request, pk=None):
        problem = self.get_object()
        to_recipients = _validated_email_list(request.data.get('to'))
        cc_recipients = _validated_email_list(request.data.get('cc'))
        subject = str(request.data.get('subject') or f'Ticket #{problem.problem_number}')[:500]
        body = str(request.data.get('body') or '')
        if not to_recipients:
            return Response({'detail': 'At least one valid recipient is required.'}, status=status.HTTP_400_BAD_REQUEST)

        images = list(problem.images.filter(include_in_customer_notification=True))
        attachments = list(problem.attachments.filter(include_in_customer_notification=True))
        total_bytes = sum((item.image.size if item.image else 0) for item in images) + sum(item.size_bytes for item in attachments)
        if total_bytes > MAX_NOTIFICATION_FILES_BYTES:
            return Response({'detail': 'Files selected for the customer notification exceed the 20 MB email attachment limit. Uncheck one or more files and try again.'}, status=status.HTTP_400_BAD_REQUEST)

        message = EmailMessage(policy=policy.SMTP)
        message['To'] = ', '.join(to_recipients)
        if cc_recipients:
            message['Cc'] = ', '.join(cc_recipients)
        message['Subject'] = subject
        # Outlook treats X-Unsent: 1 .eml files as unsent drafts in supported desktop versions.
        message['X-Unsent'] = '1'
        message.set_content(body)

        for image in images:
            stored_filename = os.path.basename(image.image.name) or 'image'
            filename = stored_filename if stored_filename.lower().endswith('.webp') else (image.original_name or stored_filename)
            _add_message_file(message, image.image, filename, mimetypes.guess_type(stored_filename)[0] or 'application/octet-stream')
        for attachment in attachments:
            filename = attachment.original_name or os.path.basename(attachment.file.name) or 'attachment'
            _add_message_file(message, attachment.file, filename, attachment.content_type)

        response = HttpResponse(message.as_bytes(), content_type='message/rfc822')
        response['Content-Disposition'] = f'attachment; filename="ticket-{problem.problem_number}-customer-notification.eml"'
        return response

    @action(detail=True, methods=['post'], url_path='customer-notification-sent')
    @transaction.atomic
    def customer_notification_sent(self, request, pk=None):
        return self._record_customer_notification_sent(
            request, ProblemSample.objects.select_for_update().get(pk=self.get_object().pk),
            str(request.data.get('tracking_token') or request.data.get('acknowledgement_token') or '').strip(),
            str(request.data.get('delivery_method') or '').strip().lower(),
        )

    def _record_customer_notification_sent(self, request, problem, supplied_token, delivery_method, prepared_token=None):
        if delivery_method not in {'mailto', 'eml'}:
            delivery_method = ''

        # A new ticket tracking link does not exist in the database until this
        # explicit confirmation. The email preparation step returns a temporary token
        # to the browser only. Previously persisted tokens are reused on resends.
        stored_link = problem.tracking_link_record_or_none
        stored_credentials = stored_link is not None
        credential_fields = []

        if stored_credentials:
            if supplied_token and supplied_token != str(stored_link.tracking_token):
                return Response({'detail': 'The prepared ticket tracking link is no longer current. Prepare the tracking-link email again.'}, status=status.HTTP_409_CONFLICT)
        else:
            if not supplied_token:
                return Response({'detail': 'Prepare the customer notification before confirming that it was sent.'}, status=status.HTTP_400_BAD_REQUEST)
            if not is_strong_tracking_token(supplied_token):
                return Response({'detail': 'Invalid ticket tracking token.'}, status=status.HTTP_400_BAD_REQUEST)
            if supplied_token != (prepared_token or problem.pending_tracking_token):
                return Response({'detail': 'The prepared tracking link is no longer current. Prepare the tracking-link email again.'}, status=status.HTTP_409_CONFLICT)
            if ProblemTrackingLink.objects.filter(tracking_token=supplied_token).exists():
                return Response({'detail': 'The prepared ticket tracking link conflicts with another ticket. Prepare the tracking-link email again.'}, status=status.HTTP_409_CONFLICT)
            stored_link = ProblemTrackingLink.objects.create(
                ticket=problem,
                tracking_token=supplied_token,
                expires_at=problem.expected_tracking_link_expiration(),
            )
            # Keep this instance synchronized so existing serializer/API aliases
            # immediately see the newly-created related row without another query.
            problem.tracking_link_record = stored_link
            problem.pending_tracking_token = None
            credential_fields.append('pending_tracking_token')

        # Preserve the previous workflow: the first confirmed customer email
        # activates automatic disposal. The activation now lives in the dedicated
        # Dispose Automatically field without changing Status or Current Workflow. Resends do not
        # reset the countdown unless the field is later changed No -> Yes again.
        first_notification = problem.customer_notified_at is None
        changes = []
        update_fields = list(credential_fields)

        if first_notification:
            now = timezone.now()
            before_status = problem.workflow_status
            before_auto = problem.dispose_automatically
            before_disposal_days = _automatic_disposal_history_value(problem)
            problem.customer_notified_at = now
            update_fields.append('customer_notified_at')

            if not before_auto and before_status == CURRENT_WORKFLOW_DEFAULT:
                values = dict(problem.custom_values or {})
                values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_YES
                problem.custom_values = values
                problem.modified_by = request.user
                update_fields.extend(['custom_values', 'modified_by'])
                update_fields.extend(problem.apply_acknowledgement_status_transition(
                    before_status, previous_dispose_automatically=before_auto, changed_at=now
                ))
                changes.append({
                    'field': 'Dispose Automatically',
                    'before': DISPOSE_AUTOMATICALLY_NO,
                    'after': DISPOSE_AUTOMATICALLY_YES,
                })
                after_disposal_days = _automatic_disposal_history_value(problem)
                if before_disposal_days != after_disposal_days:
                    changes.append({
                        'field': 'Days until up for disposal',
                        'before': before_disposal_days,
                        'after': after_disposal_days,
                    })

        if update_fields:
            problem.save(update_fields=list(dict.fromkeys(update_fields)))

        history = ProblemHistory.objects.create(
            problem=problem,
            action=ProblemHistory.ACTION_CUSTOMER_NOTIFICATION,
            actor=request.user,
            summary='Sent tracking link to customer by email',
            details={
                'delivery_method': delivery_method,
                'confirmation': 'User confirmed the customer notification email was sent.',
                'first_notification': first_notification,
                'starts_pt_clock': bool(first_notification and changes),
                'automatic_disposal_activated': bool(first_notification and changes),
                'acknowledgement_credentials_saved': bool(credential_fields),
                'changes': changes,
            },
        )
        problem.transition_to_disposal_if_due(now=timezone.now())
        problem.refresh_from_db(fields=['customer_notified_at', 'custom_values', 'modified_by'])
        serialized = ProblemSampleSerializer(problem, context={'request': request}).data
        return Response({
            'id': history.id,
            'action': history.action,
            'summary': history.summary,
            'created_at': history.created_at,
            'customer_notified_at': serialized.get('customer_notified_at'),
            'expires_at': serialized.get('expires_at'),
            'expiration_status': serialized.get('expiration_status'),
            'pt_days': serialized.get('pt_days'),
            'workflow_status': problem.workflow_status,
            'automatic_disposal_activated': bool(first_notification and changes),
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='prepare-comment-mentions')
    def prepare_comment_mentions(self, request, pk=None):
        """Build mention emails without saving the follow-up entry."""
        problem = self.get_object()
        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'detail': 'Comment cannot be blank.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(body) > 10000:
            return Response({'detail': 'Comment must be 10,000 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        mentioned_users, unavailable, groups, direct_user_ids = _resolve_mentions(body)
        if unavailable:
            handles = ', '.join(f'@{_mention_handle(user)}' for user in unavailable)
            return Response(
                {'detail': f'{handles} cannot be mentioned until their ALS email is set.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # @CustomerService only represents staff accounts that can actually be
        # mentioned. If none have ALS email yet, do not silently save a dead
        # group mention.
        if MENTION_GROUP_CUSTOMER_SERVICE in groups:
            customer_service_users = [
                user for user in mentioned_users
                if getattr(getattr(user, 'tracker_profile', None), 'role', '') == UserProfile.ROLE_CUSTOMER_SERVICE
            ]
            if not customer_service_users:
                return Response(
                    {'detail': 'No Customer Service users with ALS emails are available to mention.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        recipients = _mention_delivery_addresses(mentioned_users, groups, direct_user_ids)
        if not recipients:
            return Response({'requires_email': False, 'emails': [], 'confirmation_token': ''})

        payload = _mention_confirmation_payload(
            problem, request.user, body, mentioned_users, groups, direct_user_ids,
        )
        token = signing.dumps(payload, salt='problem-comment-mention-email', compress=True)
        return Response({
            'requires_email': True,
            # One follow-up always produces one email, even when multiple
            # people/groups were mentioned.
            'emails': [
                _mention_email(problem, request.user, mentioned_users, groups, direct_user_ids, body)
            ],
            'confirmation_token': token,
        })

    @action(detail=True, methods=['post'])
    def comments(self, request, pk=None):
        problem = self.get_object()
        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'detail': 'Comment cannot be blank.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(body) > 10000:
            return Response({'detail': 'Comment must be 10,000 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        mentioned_users, unavailable, groups, direct_user_ids = _resolve_mentions(body)
        if unavailable:
            handles = ', '.join(f'@{_mention_handle(user)}' for user in unavailable)
            return Response(
                {'detail': f'{handles} cannot be mentioned until their ALS email is set.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if MENTION_GROUP_CUSTOMER_SERVICE in groups:
            customer_service_users = [
                user for user in mentioned_users
                if getattr(getattr(user, 'tracker_profile', None), 'role', '') == UserProfile.ROLE_CUSTOMER_SERVICE
            ]
            if not customer_service_users:
                return Response(
                    {'detail': 'No Customer Service users with ALS emails are available to mention.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        recipients = _mention_delivery_addresses(mentioned_users, groups, direct_user_ids)
        requires_email = bool(recipients)
        if requires_email:
            token = str(request.data.get('mention_email_confirmation_token') or '').strip()
            if not token:
                return Response(
                    {'detail': 'Send the required mention email before saving this comment.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                confirmed = signing.loads(
                    token, salt='problem-comment-mention-email', max_age=15 * 60,
                )
            except signing.SignatureExpired:
                return Response(
                    {'detail': 'The mention email confirmation expired. Reopen the email preview and send it again.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except signing.BadSignature:
                return Response(
                    {'detail': 'The mention email confirmation is invalid. Reopen the email preview.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            expected = _mention_confirmation_payload(
                problem, request.user, body, mentioned_users, groups, direct_user_ids,
            )
            if confirmed != expected:
                return Response(
                    {'detail': 'The comment or mention recipients changed. Reopen the email preview before saving.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        confirmed_at = timezone.now() if requires_email else None
        with transaction.atomic():
            comment = ProblemComment.objects.create(problem=problem, body=body, author=request.user)
            mention_payload = []
            for mentioned_user in mentioned_users:
                ProblemMention.objects.create(
                    comment=comment,
                    problem=problem,
                    mentioned_user=mentioned_user,
                    mentioned_by=request.user,
                    notified_email=_mention_notified_email(mentioned_user, groups, direct_user_ids),
                    email_confirmed_at=confirmed_at,
                )
                mention_payload.append(_mention_user_payload(mentioned_user))
            ProblemHistory.objects.create(
                problem=problem, action=ProblemHistory.ACTION_COMMENT, actor=request.user,
                summary='Added comment', details={
                    'comment': body,
                    'mentions': mention_payload,
                    'mention_groups': [
                        '@Lab' if group == MENTION_GROUP_LAB else '@CustomerService'
                        for group in groups
                    ],
                    'mention_email_recipients': recipients,
                    'mention_email_confirmed': requires_email,
                },
            )
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='mention-users')
    def mention_users(self, request):
        query = str(request.query_params.get('q') or '').strip()[:80]
        users = (User.objects.filter(is_active=True, email__iendswith=MENTION_EMAIL_SUFFIX)
                 .exclude(email='')
                 .select_related('tracker_profile'))
        if query:
            users = users.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )
        candidates = users.order_by('first_name', 'last_name', 'username')[:60]
        valid_users = [user for user in candidates if user_has_als_email(user)][:20]
        return Response(
            _mention_group_payloads(query)
            + [_mention_user_payload(user) for user in valid_users]
        )

    @action(detail=False, methods=['get'], url_path='mentions')
    def mention_inbox(self, request):
        mentions = ProblemMention.objects.filter(mentioned_user=request.user)
        if str(request.query_params.get('summary') or '').lower() in {'1', 'true', 'yes'}:
            return Response({'unread_count': mentions.filter(read_at__isnull=True).count()})
        mentions = (mentions.select_related('problem__table', 'comment', 'mentioned_by')
                    .order_by('-created_at', '-id')[:200])
        return Response({
            'unread_count': ProblemMention.objects.filter(mentioned_user=request.user, read_at__isnull=True).count(),
            'results': [
                {
                    'id': mention.id,
                    'ticket_id': str(mention.problem_id),
                    'problem_number': mention.problem.problem_number,
                    'table_name': mention.problem.table.name if mention.problem.table_id else '',
                    'comment': mention.comment.body,
                    'mentioned_by_username': _mention_handle(mention.mentioned_by) if mention.mentioned_by else '',
                    'mentioned_by_name': (mention.mentioned_by.get_full_name().strip() or mention.mentioned_by.username) if mention.mentioned_by else 'Unknown user',
                    'created_at': mention.created_at,
                    'read_at': mention.read_at,
                }
                for mention in mentions
            ],
        })

    @action(detail=False, methods=['post'], url_path=r'mentions/(?P<mention_id>\d+)/read')
    def mark_mention_read(self, request, mention_id=None):
        updated = ProblemMention.objects.filter(
            pk=mention_id, mentioned_user=request.user, read_at__isnull=True
        ).update(read_at=timezone.now())
        if not ProblemMention.objects.filter(pk=mention_id, mentioned_user=request.user).exists():
            return Response({'detail': 'Mention not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'read': True, 'updated': bool(updated)})

    @action(detail=False, methods=['post'], url_path='mentions/mark-all-read')
    def mark_all_mentions_read(self, request):
        updated = ProblemMention.objects.filter(
            mentioned_user=request.user, read_at__isnull=True
        ).update(read_at=timezone.now())
        return Response({'updated': updated})


class ProblemContainerViewSet(viewsets.ModelViewSet):
    queryset = (ProblemContainer.objects.select_related('created_by', 'disposed_by')
                .prefetch_related('problem_samples__table')
                .order_by('-id'))
    serializer_class = ProblemContainerSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def perform_create(self, serializer):
        # The serializer is read-only because IDs are system generated, so create
        # the container directly and let create() return its generated Container ID.
        return None

    def create(self, request, *args, **kwargs):
        container = ProblemContainer.objects.create(created_by=request.user)
        return Response(
            self.get_serializer(container).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'], url_path='lookup')
    def lookup(self, request):
        identifier = request.query_params.get('container_id') or request.query_params.get('id') or ''
        container = ProblemContainer.resolve_identifier(identifier)
        if not container:
            return Response({'detail': 'Container not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(container).data)

    def _apply_container_disposal(self, request, container, samples, disposal_samples, reason, *, history_extra=None):
        now = timezone.now()
        disposal_snapshot = {}
        history_extra = dict(history_extra or {})
        for sample in disposal_samples:
            values = dict(sample.custom_values or {})
            before = sample.workflow_status
            before_auto = sample.dispose_automatically
            disposal_snapshot[str(sample.id)] = {
                'current_workflow': sample.current_workflow,
                'custom_values': dict(sample.custom_values or {}),
                'modified_by_id': sample.modified_by_id,
                'acknowledged_at': sample.acknowledged_at.isoformat() if sample.acknowledged_at else None,
                'acknowledgement_status_changed_at': (
                    sample.acknowledgement_status_changed_at.isoformat()
                    if sample.acknowledgement_status_changed_at else None
                ),
                'customer_acknowledgement_action': sample.customer_acknowledgement_action,
                'automatic_disposal_started_at': (
                    sample.automatic_disposal_started_at.isoformat()
                    if sample.automatic_disposal_started_at else None
                ),
            }
            values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_DISPOSED
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
            modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier
            sample.custom_values = values
            sample.current_workflow = PROBLEM_STATUS_DISPOSED
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(
                before, previous_dispose_automatically=before_auto, changed_at=now,
            )
            sample.save(update_fields=list(dict.fromkeys([
                'custom_values', 'current_workflow', 'modified_by', 'modified_at', *lifecycle_fields,
            ])))
            if before != PROBLEM_STATUS_DISPOSED:
                details = {
                    'changes': [{
                        'field': 'Current Workflow',
                        'before': before or '—',
                        'after': PROBLEM_STATUS_DISPOSED,
                    }],
                    **history_extra,
                }
                ProblemHistory.objects.create(
                    problem=sample, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
                    summary=f'Container {container.container_id} disposed',
                    details=_history_details(details, reason),
                )

        container.disposed_at = now
        container.disposed_by = request.user
        # Distinguish an all-Disposed container from legacy disposals that had
        # no snapshot and still need a history-based rollback.
        container.disposal_snapshot = disposal_snapshot or {'_no_rows_changed': True}
        container.save(update_fields=['disposed_at', 'disposed_by', 'disposal_snapshot'])
        if hasattr(container, '_container_samples_cache'):
            delattr(container, '_container_samples_cache')
        return Response(self.get_serializer(container).data)

    @action(detail=True, methods=['post'], url_path='dispose')
    @transaction.atomic
    def dispose(self, request, pk=None):
        container = ProblemContainer.objects.select_for_update().get(pk=pk)
        if container.disposed_at:
            return Response(self.get_serializer(container).data)
        reason = _change_reason(request)
        samples = list(container.problem_samples.select_related('table').prefetch_related('table__columns'))
        if not samples:
            return Response({'detail': 'An empty container cannot be disposed.'}, status=status.HTTP_409_CONFLICT)

        blocked = [sample for sample in samples if sample.workflow_status not in {PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_DISPOSED}]
        if blocked:
            return Response({
                'detail': 'This container is not ready to be disposed. Every attached ticket must have Current Workflow = To be Disposed or Disposed.',
                'blocking_problem_ids': [sample.problem_number for sample in blocked],
            }, status=status.HTTP_409_CONFLICT)

        disposal_samples = [sample for sample in samples if sample.workflow_status == PROBLEM_STATUS_TO_BE_DISPOSED]
        return self._apply_container_disposal(request, container, samples, disposal_samples, reason)

    @action(detail=True, methods=['post'], url_path='dispose-by-date')
    @transaction.atomic
    def dispose_by_date(self, request, pk=None):
        raw_cutoff = str(request.data.get('cutoff_date') or '').strip()
        cutoff = parse_date(raw_cutoff)
        if not cutoff:
            return Response(
                {'detail': 'Provide a valid cutoff_date in YYYY-MM-DD format.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        container = ProblemContainer.objects.select_for_update().get(pk=pk)
        if container.disposed_at:
            return Response(self.get_serializer(container).data)

        reason = _change_reason(request)
        samples = list(container.problem_samples.select_related('table').prefetch_related('table__columns'))
        if not samples:
            return Response({'detail': 'An empty container cannot be disposed.'}, status=status.HTTP_409_CONFLICT)

        # "Older than" is intentionally strict: a ticket created on the cutoff
        # date itself is not old enough. Use the application's local timezone so
        # the server and the date-only UI agree at midnight boundaries.
        blocked = [sample for sample in samples if timezone.localdate(sample.created_at) >= cutoff]
        if blocked:
            return Response({
                'detail': f'Every ticket in this container must have been created before {cutoff.isoformat()}.',
                'blocking_problem_ids': [sample.problem_number for sample in blocked],
                'cutoff_date': cutoff.isoformat(),
            }, status=status.HTTP_409_CONFLICT)

        disposal_samples = [sample for sample in samples if sample.workflow_status != PROBLEM_STATUS_DISPOSED]
        return self._apply_container_disposal(
            request,
            container,
            samples,
            disposal_samples,
            reason,
            history_extra={
                'disposal_method': 'dispose_by_date',
                'cutoff_date': cutoff.isoformat(),
            },
        )

    @action(detail=True, methods=['post'], url_path='undo-disposal')
    @transaction.atomic
    def undo_disposal(self, request, pk=None):
        container = ProblemContainer.objects.select_for_update().get(pk=pk)
        if not container.disposed_at:
            return Response({'detail': 'This container has not been disposed.'}, status=status.HTTP_409_CONFLICT)

        reason = _change_reason(request)
        samples = list(container.problem_samples.select_related('table').prefetch_related('table__columns'))
        snapshot = container.disposal_snapshot or {}

        # A stamped container whose tickets were already Disposed needs only
        # its stamp cleared. Legacy empty snapshots still use History fallback.
        if snapshot.get('_no_rows_changed') is True:
            rollback_samples = []
        elif snapshot:
            rollback_ids = set(snapshot.keys())
            rollback_samples = [sample for sample in samples if str(sample.id) in rollback_ids]
            missing_snapshot_samples = rollback_ids - {str(sample.id) for sample in rollback_samples}
            if missing_snapshot_samples:
                return Response({
                    'detail': 'Container disposal cannot be undone because one or more disposed samples are no longer assigned to this container.',
                }, status=status.HTTP_409_CONFLICT)
        else:
            rollback_samples = samples

        not_disposed = [sample for sample in rollback_samples if sample.workflow_status != PROBLEM_STATUS_DISPOSED]
        if not_disposed:
            return Response({
                'detail': 'Container disposal cannot be undone because one or more samples changed by disposal were changed again afterward.',
                'blocking_problem_ids': [sample.problem_number for sample in not_disposed],
            }, status=status.HTTP_409_CONFLICT)

        restore_plan = []
        missing = []
        history_summary = f'Container {container.container_id} disposed'
        for sample in rollback_samples:
            saved = snapshot.get(str(sample.id))
            if saved is not None:
                saved_values = saved.get('custom_values') or {}
                before = str(
                    saved_values.get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY)
                    or saved.get('current_workflow')
                    or CURRENT_WORKFLOW_DEFAULT
                )
                restore_plan.append((sample, before, saved))
                continue

            # Backward-compatible fallback for containers disposed before rollback snapshots existed.
            disposal_history = sample.history.filter(summary=history_summary).order_by('-created_at', '-id').first()
            before = ''
            if disposal_history:
                for change in (disposal_history.details or {}).get('changes', []):
                    if str(change.get('field') or '').strip().lower() in {'current workflow', 'status'}:
                        before = str(change.get('before') or '')
                        if before == '—':
                            before = ''
                        break
            if not disposal_history:
                missing.append(sample.problem_number)
            else:
                restore_plan.append((sample, before, None))

        if missing:
            return Response({
                'detail': 'Container disposal cannot be undone because the previous Current Workflow could not be recovered for every sample.',
                'blocking_problem_ids': missing,
            }, status=status.HTTP_409_CONFLICT)

        now = timezone.now()
        for sample, before, saved in restore_plan:
            if saved is not None:
                sample.custom_values = dict(saved.get('custom_values') or {})
                sample.current_workflow = before or CURRENT_WORKFLOW_DEFAULT
                sample.custom_values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = sample.current_workflow
                sample.modified_by_id = saved.get('modified_by_id')
                sample.acknowledged_at = parse_datetime(saved.get('acknowledged_at')) if saved.get('acknowledged_at') else None
                if sample.workflow_status == CURRENT_WORKFLOW_DEFAULT:
                    # CS Follow-Up reactivates the persistent tracking link,
                    # so an old routed-workflow expiry anchor must not be restored.
                    sample.acknowledgement_status_changed_at = None
                else:
                    sample.acknowledgement_status_changed_at = (
                        parse_datetime(saved.get('acknowledgement_status_changed_at'))
                        if saved.get('acknowledgement_status_changed_at') else None
                    )
                sample.customer_acknowledgement_action = str(saved.get('customer_acknowledgement_action') or '')
                saved_auto_started = saved.get('automatic_disposal_started_at')
                if saved_auto_started:
                    sample.automatic_disposal_started_at = parse_datetime(saved_auto_started)
                elif sample.dispose_automatically:
                    # Legacy snapshots may not store the countdown anchor. If the
                    # restored row has Dispose Automatically = Yes, treat undo as a
                    # fresh activation rather than leaving an active row without an anchor.
                    sample.automatic_disposal_started_at = now
                else:
                    sample.automatic_disposal_started_at = None
                update_fields = [
                    'custom_values', 'current_workflow', 'modified_by', 'modified_at',
                    'acknowledged_at', 'acknowledgement_status_changed_at', 'customer_acknowledgement_action',
                    'automatic_disposal_started_at',
                ]
            else:
                values = dict(sample.custom_values or {})
                restored_workflow = before if before in CURRENT_WORKFLOW_CHOICES else CURRENT_WORKFLOW_DEFAULT
                values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = restored_workflow
                sample.custom_values = values
                sample.current_workflow = restored_workflow
                sample.modified_by = request.user
                lifecycle_fields = sample.apply_acknowledgement_status_transition(
                    PROBLEM_STATUS_DISPOSED, previous_dispose_automatically=False, changed_at=now
                )
                update_fields = list(dict.fromkeys(
                    ['custom_values', 'current_workflow', 'modified_by', 'modified_at'] + lifecycle_fields
                ))

            sample.save(update_fields=update_fields)
            if saved is not None:
                sample.set_tracking_link_expiration(sample.expected_tracking_link_expiration())
            ProblemHistory.objects.create(
                problem=sample, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
                summary=f'Container {container.container_id} disposal undone',
                details=_history_details({'changes': [{'field': 'Current Workflow', 'before': PROBLEM_STATUS_DISPOSED, 'after': before or '—'}]}, reason),
            )

        container.disposed_at = None
        container.disposed_by = None
        container.disposal_snapshot = {}
        container.save(update_fields=['disposed_at', 'disposed_by', 'disposal_snapshot'])
        if hasattr(container, '_container_samples_cache'):
            delattr(container, '_container_samples_cache')
        return Response(self.get_serializer(container).data)


class ProblemTableViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsTrackerAdminOrReadOnly]
    queryset = ProblemTable.objects.prefetch_related('columns').select_related('created_by')
    serializer_class = ProblemTableSerializer

    @action(detail=True, methods=['post'], url_path='reorder-columns')
    @transaction.atomic
    def reorder_columns(self, request, pk=None):
        table = self.get_object()
        column_ids = request.data.get('column_ids')
        if not isinstance(column_ids, list):
            return Response({'detail': 'column_ids must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

        requested = [str(value) for value in column_ids]
        if len(requested) != len(set(requested)):
            return Response({'detail': 'Each field may appear only once in the field order.'}, status=status.HTTP_400_BAD_REQUEST)

        columns = list(ProblemColumn.objects.select_for_update().filter(table=table))
        by_id = {str(column.id): column for column in columns}
        if set(requested) != set(by_id) or len(requested) != len(columns):
            return Response({
                'detail': 'Field order must contain every field in this table exactly once.'
            }, status=status.HTTP_400_BAD_REQUEST)

        changed = []
        for position, column_id in enumerate(requested):
            column = by_id[column_id]
            if column.position != position:
                column.position = position
                changed.append(column)
        if changed:
            ProblemColumn.objects.bulk_update(changed, ['position'])

        refreshed = ProblemTable.objects.prefetch_related('columns').select_related('created_by').get(pk=table.pk)
        return Response(ProblemTableSerializer(refreshed, context=self.get_serializer_context()).data)

    def perform_create(self, serializer):
        table = serializer.save(created_by=self.request.user)
        ensure_builtin_columns(table)

    def destroy(self, request, *args, **kwargs):
        table = self.get_object()
        if table.is_default:
            return Response({'detail': 'The default table cannot be deleted.'}, status=status.HTTP_409_CONFLICT)
        if table.problem_samples.exists():
            return Response({'detail': 'This table contains tickets. Remove or archive them before deleting the table.'}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)




def _synchronize_intercolumn_controller_rows(table):
    """Apply current controller rules to all rows after a rule-definition change."""
    for sample in table.problem_samples.select_related('table').prefetch_related('table__columns'):
        before_values = dict(sample.custom_values or {})
        before_workflow = sample.workflow_status
        before_auto = sample.dispose_automatically
        try:
            update_fields = sample.apply_acknowledgement_status_transition(
                before_workflow,
                previous_dispose_automatically=before_auto,
                changed_at=timezone.now(),
                strict_intercolumn=True,
            )
        except DjangoValidationError as exc:
            messages = getattr(exc, 'messages', None) or [str(exc)]
            raise DRFValidationError({'intercolumn_rules': messages}) from exc
        if not update_fields:
            continue
        update_fields = list(dict.fromkeys([*update_fields, 'modified_at']))
        sample.save(update_fields=update_fields)
        after_values = dict(sample.custom_values or {})
        changed_keys = sorted(key for key in set(before_values) | set(after_values) if before_values.get(key) != after_values.get(key))
        if changed_keys:
            names = {column.field_key: column.name for column in table.columns.all()}
            ProblemHistory.objects.create(
                problem=sample,
                action=ProblemHistory.ACTION_UPDATED,
                actor=None,
                summary='Intercolumn value rules applied',
                details={
                    'automatic': True,
                    'changes': [
                        {
                            'field': names.get(key, key),
                            'before': _history_value(before_values.get(key)),
                            'after': _history_value(after_values.get(key)),
                        }
                        for key in changed_keys
                    ],
                },
            )



class ProblemColumnViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsTrackerAdminOrReadOnly]
    queryset = ProblemColumn.objects.select_related('table', 'depends_on_column')
    serializer_class = ProblemColumnSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        column = serializer.save()
        if column.column_type == ProblemColumn.TYPE_ROW_CREATOR:
            for problem in column.table.problem_samples.select_related('created_by').only(
                    'id', 'custom_values', 'legacy_created_by', 'created_by__email', 'created_by__username'):
                values = dict(problem.custom_values or {})
                creator = (
                    (problem.created_by.email if problem.created_by else '')
                    or (problem.created_by.username if problem.created_by else '')
                    or problem.legacy_created_by
                    or ''
                ).strip()
                values[column.field_key] = creator
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
            return

        if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
            for problem in column.table.problem_samples.select_related('modified_by', 'created_by').only(
                    'id', 'custom_values', 'legacy_modified_by', 'legacy_created_by',
                    'modified_by__email', 'modified_by__username', 'created_by__email', 'created_by__username'):
                values = dict(problem.custom_values or {})
                modifier = (
                    (problem.modified_by.email if problem.modified_by else '')
                    or (problem.modified_by.username if problem.modified_by else '')
                    or problem.legacy_modified_by
                    or (problem.created_by.email if problem.created_by else '')
                    or (problem.created_by.username if problem.created_by else '')
                    or problem.legacy_created_by
                    or ''
                ).strip()
                values[column.field_key] = modifier
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
            return

        if column.column_type == ProblemColumn.TYPE_DATE_TODAY:
            today_value = timezone.localdate().isoformat()
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                values[column.field_key] = today_value
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
            return

        default = column.default_value
        has_default = not (default is None or default == '' or default == [])
        if has_default:
            # Adding a column behaves like a Microsoft List column: the chosen
            # default immediately fills that column for rows already in the table.
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                values[column.field_key] = default
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)

        if column.column_type == ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER:
            _synchronize_intercolumn_controller_rows(column.table)

    @transaction.atomic
    def perform_update(self, serializer):
        previous_type = serializer.instance.column_type
        previous_rules = list(serializer.instance.intercolumn_rules or [])
        previous_dependencies = list(serializer.instance.client_email_dependencies or [])
        if not previous_dependencies and serializer.instance.depends_on_column_id:
            previous_dependencies = [str(serializer.instance.depends_on_column_id)]
        column = serializer.save()
        if column.column_type == ProblemColumn.TYPE_ROW_CREATOR:
            # Converting an existing column to Row Creator discards the old cell
            # values and rebuilds each row from its immutable creator metadata.
            for problem in column.table.problem_samples.select_related('created_by').only(
                    'id', 'custom_values', 'legacy_created_by', 'created_by__email', 'created_by__username'):
                values = dict(problem.custom_values or {})
                creator = (
                    (problem.created_by.email if problem.created_by else '')
                    or (problem.created_by.username if problem.created_by else '')
                    or problem.legacy_created_by
                    or ''
                ).strip()
                values[column.field_key] = creator
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
            return

        if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
            # Converting an existing column rebuilds each row from its latest
            # recorded modifier metadata, with creator metadata as a legacy fallback.
            for problem in column.table.problem_samples.select_related('modified_by', 'created_by').only(
                    'id', 'custom_values', 'legacy_modified_by', 'legacy_created_by',
                    'modified_by__email', 'modified_by__username', 'created_by__email', 'created_by__username'):
                values = dict(problem.custom_values or {})
                modifier = (
                    (problem.modified_by.email if problem.modified_by else '')
                    or (problem.modified_by.username if problem.modified_by else '')
                    or problem.legacy_modified_by
                    or (problem.created_by.email if problem.created_by else '')
                    or (problem.created_by.username if problem.created_by else '')
                    or problem.legacy_created_by
                    or ''
                ).strip()
                values[column.field_key] = modifier
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
            return

        if column.column_type == ProblemColumn.TYPE_DATE_TODAY and previous_type != ProblemColumn.TYPE_DATE_TODAY:
            # Preserve valid dates when converting a Date column. Any empty or
            # incompatible historical cell receives today's date so the new
            # Date (Today) type is immediately valid.
            today_value = timezone.localdate().isoformat()
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                current = values.get(column.field_key)
                if not isinstance(current, str) or parse_date(current) is None:
                    values[column.field_key] = today_value
                    ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
            return

        if column.column_type == ProblemColumn.TYPE_FIXED:
            # A Fixed Value is table-wide. Changing it updates every existing row
            # immediately so exports and direct JSON consumers remain consistent.
            fixed_value = column.default_value
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                values[column.field_key] = fixed_value
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
            return

        if column.column_type == ProblemColumn.TYPE_GROUP:
            # If the configured group changes, remove row assignments that no
            # longer belong to that group. Historical row activity remains in
            # the audit trail, while the current cell stays semantically valid.
            eligible = set(UserProfile.objects.filter(
                role=column.group_role, user__is_active=True,
            ).select_related('user').values_list('user__email', flat=True))
            eligible = {str(email or '').strip().lower() for email in eligible if email}
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                current = values.get(column.field_key)
                if current and str(current).strip().lower() not in eligible:
                    values[column.field_key] = column.default_value if column.default_value not in (None, '', []) else None
                    ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)

        current_dependencies = [str(value) for value in (column.client_email_dependencies or []) if value]
        if (column.column_type == ProblemColumn.TYPE_CLIENT_EMAIL
                and (previous_type != ProblemColumn.TYPE_CLIENT_EMAIL
                     or previous_dependencies != current_dependencies)):
            # Client Email is now a multi-address row-local list. When its source
            # dependency chain changes, mark existing values as uninitialized so
            # the editor can load the new active company's suggestions the next
            # time the row is edited. Do not try to infer which old addresses were
            # imported suggestions versus manually-added addresses.
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                if column.field_key in values:
                    values[column.field_key] = ''
                    ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)

        if column.column_type == ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER:
            if previous_type != ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER or previous_rules != list(column.intercolumn_rules or []):
                _synchronize_intercolumn_controller_rows(column.table)

    def get_queryset(self):
        queryset = super().get_queryset()
        table_id = self.request.query_params.get('table')
        if table_id:
            queryset = queryset.filter(table_id=table_id)

        # Dashboard "See samples" links carry an opened_range so the user
        # lands in the selected ticket table with the same date window that
        # produced the dashboard card count. Keep this filtering at queryset
        # level so normal search and advanced search continue to respect it.
        opened_range = str(self.request.query_params.get('opened_range') or '').strip().lower()
        if opened_range:
            from .dashboard_views import WINDOWS, _custom_bounds
            if opened_range in WINDOWS:
                queryset = queryset.filter(created_at__gte=timezone.now() - WINDOWS[opened_range])
            elif opened_range == 'custom':
                try:
                    _, _, start_at, end_at = _custom_bounds(
                        self.request.query_params.get('start_date'),
                        self.request.query_params.get('end_date'),
                    )
                except ValueError:
                    return queryset.none()
                queryset = queryset.filter(created_at__gte=start_at, created_at__lt=end_at)
        return queryset

    def destroy(self, request, *args, **kwargs):
        column = self.get_object()
        if column.is_system:
            return Response({'detail': 'Built-in columns cannot be deleted.'}, status=status.HTTP_409_CONFLICT)
        referenced_by = []
        for controller in column.table.columns.filter(column_type=ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER).exclude(pk=column.pk):
            if any(str(rule.get('other_column_id') or '') == str(column.pk) for rule in (controller.intercolumn_rules or [])):
                referenced_by.append(controller.name)
        if referenced_by:
            return Response({
                'detail': f'Remove the Intercolumn Value Controller rule(s) in {", ".join(referenced_by)} before deleting this column.'
            }, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)

    @transaction.atomic
    def perform_destroy(self, instance):
        field_key = instance.field_key
        table = instance.table
        removed_id = str(instance.id)

        # Remove this field from any prioritized Client Email dependency chains.
        dependent_email_columns = list(table.columns.filter(column_type=ProblemColumn.TYPE_CLIENT_EMAIL).exclude(pk=instance.pk))
        affected_email_columns = []
        for email_column in dependent_email_columns:
            dependencies = [str(value) for value in (email_column.client_email_dependencies or []) if value]
            if not dependencies and email_column.depends_on_column_id:
                dependencies = [str(email_column.depends_on_column_id)]
            if removed_id not in dependencies:
                continue
            affected_email_columns.append(email_column)
            dependencies = [value for value in dependencies if value != removed_id]
            email_column.client_email_dependencies = dependencies
            next_first = table.columns.filter(pk=dependencies[0]).first() if dependencies else None
            email_column.depends_on_column = next_first
            email_column.save(update_fields=['client_email_dependencies', 'depends_on_column', 'modified_at'])

        for problem in table.problem_samples.only('id', 'custom_values'):
            values = dict(problem.custom_values or {})
            changed = False
            if field_key in values:
                values.pop(field_key, None)
                changed = True

            # A dependency deletion changes the source list. Mark affected Client
            # Email values as uninitialized so the editor can rebuild them from
            # the remaining prioritized dependencies on next edit.
            for email_column in affected_email_columns:
                if email_column.field_key in values:
                    values[email_column.field_key] = ''
                    changed = True

            if changed:
                ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)
        instance.delete()

class ProblemAcknowledgementView(APIView):
    """Public, tokenized ticket tracking page API. No ALS account is required."""
    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _problem(self, token, *, for_update=False):
        if not is_strong_tracking_token(token):
            return None
        queryset = (ProblemSample.objects.select_related('table', 'tracking_link_record')
                    .prefetch_related('images', 'attachments', 'table__columns')
                    .filter(tracking_link_record__tracking_token=token))
        if for_update:
            queryset = queryset.select_for_update(of=('self',))
        return queryset.first()

    def _is_link_gone(self, problem):
        return problem.tracking_link_expired

    def _public_files(self, problem):
        images = []
        for image in problem.images.all():
            try:
                size_bytes = image.image.size if image.image else 0
            except (OSError, ValueError):
                size_bytes = 0
            images.append({
                'id': image.id,
                'name': image.original_name or os.path.basename(image.image.name) or f'Image {image.id}',
                'size_bytes': size_bytes,
            })

        attachments = [{
            'id': attachment.id,
            'name': attachment.original_name or os.path.basename(attachment.file.name) or f'File {attachment.id}',
            'size_bytes': attachment.size_bytes,
            'content_type': attachment.content_type or '',
        } for attachment in problem.attachments.all()]

        return {'images': images, 'attachments': attachments}

    def _public_details(self, problem):
        """Return customer-safe problem details for the public tracking page.

        The page mirrors the fields intentionally exposed by the customer
        notification configuration. Core sample-identification/hold fields are
        also included when present so the tracking page carries the same useful
        context as the notification email. Staff-only identity/email fields are
        never exposed by this public endpoint.
        """
        values = problem.custom_values or {}
        core_labels = {
            'problemtype', 'alssampletrackingnumber', 'alstrackingnumber',
            'sampletrackingnumber', 'reasonforhold', 'holdreason',
            'reasonforsampleprocessinghold', 'issuedescription', 'issue',
            'datereceived', 'receiveddate', 'numberofproblemsamples',
            'problemsamplecount', 'numberofsamples', 'courier',
            'couriertrackingnumber', 'trackingnumber', 'distributor',
            'enduser', 'brand',
        }
        hidden_types = {
            ProblemColumn.TYPE_EMAIL, ProblemColumn.TYPE_CLIENT_EMAIL,
            ProblemColumn.TYPE_GROUP, ProblemColumn.TYPE_ROW_CREATOR,
            ProblemColumn.TYPE_RECENT_ROW_MODIFIER,
        }

        def normalize_label(label):
            return ''.join(character for character in str(label or '').lower() if character.isalnum())

        def display_value(column, raw):
            if raw in (None, '', [], {}):
                return ''
            if column.column_type == ProblemColumn.TYPE_BOOLEAN:
                if isinstance(raw, bool):
                    return 'Yes' if raw else 'No'
                lowered = str(raw).strip().lower()
                if lowered in {'true', '1', 'yes', 'y'}:
                    return 'Yes'
                if lowered in {'false', '0', 'no', 'n'}:
                    return 'No'
            if isinstance(raw, (list, tuple)):
                return ', '.join(str(item) for item in raw if str(item).strip())
            if isinstance(raw, dict):
                for key in ('name', 'label', 'value'):
                    if raw.get(key):
                        return str(raw[key])
                return ''
            return str(raw)

        fallback_values = {
            'alssampletrackingnumber': problem.als_tracking_number,
            'alstrackingnumber': problem.als_tracking_number,
            'sampletrackingnumber': problem.als_tracking_number,
            'numberofproblemsamples': problem.problem_sample_count,
            'problemsamplecount': problem.problem_sample_count,
            'numberofsamples': problem.problem_sample_count,
            'brand': problem.brand,
            'distributor': problem.distributor,
            'enduser': problem.end_user,
            'datereceived': problem.date_received,
            'receiveddate': problem.date_received,
            'problemtype': problem.problem_type,
            'reasonforhold': problem.issue_description,
            'holdreason': problem.issue_description,
            'reasonforsampleprocessinghold': problem.issue_description,
            'issuedescription': problem.issue_description,
            'issue': problem.issue_description,
            'courier': problem.courier,
            'couriertrackingnumber': problem.courier_tracking_number,
            'trackingnumber': problem.courier_tracking_number,
        }

        details = []
        for column in problem.table.columns.all():
            if column.is_system or column.column_type in hidden_types:
                continue
            normalized_label = normalize_label(column.name)
            if not column.include_in_customer_notification and normalized_label not in core_labels:
                continue
            raw = column.default_value if column.column_type == ProblemColumn.TYPE_FIXED else values.get(column.field_key)
            if raw in (None, '', [], {}) and normalized_label in fallback_values:
                raw = fallback_values[normalized_label]
            shown = display_value(column, raw).strip()
            if shown:
                details.append({
                    'label': column.name,
                    'value': shown,
                    'position': column.position,
                })
        details.sort(key=lambda item: item['position'])
        return [{'label': item['label'], 'value': item['value']} for item in details]

    def _customer_action_label(self, problem):
        """Return the customer-facing label that was actually presented/selected."""
        action = problem.customer_acknowledgement_action or ''
        if not action:
            return ''

        # Preserve the exact wording used when the customer made the choice.
        # This matters because Dispose Automatically = Yes uses a different set of
        # customer-facing labels for the same underlying workflow actions.
        for entry in problem.history.all()[:25]:
            details = entry.details if isinstance(entry.details, dict) else {}
            if details.get('customer_action') == action and details.get('customer_action_label'):
                return str(details['customer_action_label'])

        return {
            CUSTOMER_ACTION_DISPOSE: 'Dispose Sample(s)',
            CUSTOMER_ACTION_SHIP_BACK: 'Ship back samples',
            CUSTOMER_ACTION_HOLD: 'Hold sample',
            CUSTOMER_ACTION_REQUESTED_INFORMATION: 'Give us more details about this ticket',
        }.get(action, '')

    def _payload(self, problem):
        workflow_status = problem.workflow_status
        visible_until = problem.tracking_link_expires_at
        public_files = self._public_files(problem)
        public_details = {'details': self._public_details(problem)}

        # Only completed workflows lock the public response. Intermediate queues
        # ("To be ...") remain editable so a customer can revise a prior choice
        # until ALS actually disposes, returns to testing, or ships the samples.
        if workflow_status == PROBLEM_STATUS_BACK_TO_TESTING:
            return {
                'state': 'testing',
                'message': workflow_status,
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
                'customer_action': problem.customer_acknowledgement_action or '',
                'customer_action_label': self._customer_action_label(problem),
                'can_choose_action': False,
            }
        if workflow_status == PROBLEM_STATUS_DISPOSED:
            return {
                'state': 'dumped',
                'message': 'Ticket Disposed',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
                'customer_action': problem.customer_acknowledgement_action or '',
                'customer_action_label': self._customer_action_label(problem),
                'can_choose_action': False,
            }
        if workflow_status == PROBLEM_STATUS_SHIPPED_BACK:
            return {
                'state': 'shipping',
                'message': 'Samples shipped back to client',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
                'customer_action': problem.customer_acknowledgement_action or CUSTOMER_ACTION_SHIP_BACK,
                'customer_action_label': self._customer_action_label(problem) or 'Ship back',
                'can_choose_action': False,
            }

        # Customer acknowledgement is tracked independently from descriptive Status.
        # Every non-completed workflow keeps the response controls available.
        if not problem.acknowledged_at:
            if problem.dispose_automatically:
                days_remaining = problem.days_until_automatic_disposal
                if days_remaining is None:
                    message = 'These sample(s) are scheduled for eventual disposal.'
                elif days_remaining <= 0:
                    message = 'These sample(s) are up for disposal now.'
                elif days_remaining == 1:
                    message = 'These sample(s) will be up for disposal in 1 day.'
                else:
                    message = f'These sample(s) will be up for disposal in {days_remaining} days.'
                return {
                    'state': 'pending',
                    'message': message,
                    'problem_number': problem.problem_number,
                    'automatic_disposal_active': True,
                    'days_until_disposal': days_remaining,
                    'can_choose_action': True,
                    **public_details,
                    **public_files,
                }
            return {
                'state': 'pending',
                'message': 'Please choose how ALS should handle this ticket',
                'problem_number': problem.problem_number,
                'automatic_disposal_active': False,
                'can_choose_action': True,
                **public_details,
                **public_files,
            }

        return {
            'state': 'acknowledged',
            'message': 'Your response has been recorded. You can change it until ALS completes the requested workflow.',
            'problem_number': problem.problem_number,
            **public_details,
            **public_files,
            'acknowledged_at': problem.acknowledged_at,
            'visible_until': visible_until,
            'customer_action': problem.customer_acknowledgement_action or '',
            'customer_action_label': self._customer_action_label(problem),
            'can_choose_action': True,
            'automatic_disposal_active': problem.dispose_automatically,
            'days_until_disposal': problem.days_until_automatic_disposal,
        }

    def get(self, request, token):
        problem = self._problem(token)
        if not problem or self._is_link_gone(problem):
            return Response({'detail': 'Ticket tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._payload(problem))

    @transaction.atomic
    def post(self, request, token):
        problem = self._problem(token, for_update=True)
        if not problem or self._is_link_gone(problem):
            return Response({'detail': 'Ticket tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)

        workflow_status = problem.workflow_status
        # A customer may revise a response while work is only queued. Once ALS
        # completes disposal, back-to-testing, or shipping, the response is final.
        if workflow_status in {
            PROBLEM_STATUS_DISPOSED,
            PROBLEM_STATUS_BACK_TO_TESTING,
            PROBLEM_STATUS_SHIPPED_BACK,
        }:
            return Response(
                {'detail': 'This ticket workflow has been completed and the customer response can no longer be changed.'},
                status=status.HTTP_409_CONFLICT,
            )

        customer_action = str(request.data.get('action') or '').strip()
        customer_signature = ' '.join(str(request.data.get('signature') or '').split())
        if not customer_signature:
            return Response({'detail': 'Type your name as a signature before sending a response.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(customer_signature) > 200:
            return Response({'detail': 'Signature must be 200 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed_actions = {
            CUSTOMER_ACTION_DISPOSE,
            CUSTOMER_ACTION_SHIP_BACK,
            CUSTOMER_ACTION_REQUESTED_INFORMATION,
        }
        if customer_action not in allowed_actions:
            return Response({'detail': 'Choose a valid sample action.'}, status=status.HTTP_400_BAD_REQUEST)

        requested_information = str(request.data.get('requested_information') or '').strip()
        customer_image_uploads = list(request.FILES.getlist('images'))
        customer_attachment_uploads = list(request.FILES.getlist('attachments'))
        if (customer_image_uploads or customer_attachment_uploads) and customer_action != CUSTOMER_ACTION_REQUESTED_INFORMATION:
            return Response(
                {'detail': 'Customer files can only be uploaded with Give us more details about this ticket.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prepared_customer_images = []
        if customer_action == CUSTOMER_ACTION_REQUESTED_INFORMATION:
            if not requested_information:
                return Response({'detail': 'Enter the requested information before sending this response.'}, status=status.HTTP_400_BAD_REQUEST)
            if len(requested_information) > 4000:
                return Response({'detail': 'Requested information must be 4000 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

            all_customer_uploads = customer_image_uploads + customer_attachment_uploads
            if len(all_customer_uploads) > MAX_CUSTOMER_RESPONSE_FILES:
                return Response(
                    {'detail': f'Attach no more than {MAX_CUSTOMER_RESPONSE_FILES} files to one response.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if sum(getattr(uploaded, 'size', 0) or 0 for uploaded in all_customer_uploads) > MAX_CUSTOMER_RESPONSE_BYTES:
                return Response(
                    {'detail': 'The combined size of customer attachments must be 50 MB or smaller.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Fully validate/process every file before changing the ticket. Images use
            # the same WebP compression pipeline as staff uploads, keeping public
            # uploads small on the Railway media volume.
            for uploaded in customer_image_uploads:
                error = _validate_uploaded_file(uploaded, image=True)
                if error:
                    return Response({'detail': f'{uploaded.name}: {error}'}, status=status.HTTP_400_BAD_REQUEST)
                original_name = (uploaded.name or 'customer-image')[:255]
                try:
                    compressed_bytes, stored_name = compress_problem_image(uploaded, original_name)
                except (UnidentifiedImageError, OSError, ValueError):
                    return Response(
                        {'detail': f'{original_name}: The selected image could not be processed.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not compressed_bytes:
                    return Response(
                        {'detail': f'{original_name}: The selected image could not be processed.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                prepared_customer_images.append((original_name, compressed_bytes, stored_name))

            for uploaded in customer_attachment_uploads:
                error = _validate_uploaded_file(uploaded)
                if error:
                    return Response({'detail': f'{uploaded.name}: {error}'}, status=status.HTTP_400_BAD_REQUEST)

        # The first explicit customer disposition choice acknowledges receipt.
        # Acknowledgement does not change descriptive Status; workflow routing happens only
        # after the selected action is applied below.
        if not problem.acknowledged_at:
            now = timezone.now()
            problem.acknowledged_at = now
            problem.customer_acknowledgement_action = ''
            problem.save(update_fields=['acknowledged_at', 'customer_acknowledgement_action'])
            ProblemHistory.objects.create(
                problem=problem,
                action=ProblemHistory.ACTION_ACKNOWLEDGED,
                actor=None,
                summary='Customer acknowledged ticket',
                details={
                    'acknowledged_via': 'public_tracking_link',
                    'changes': [],
                },
            )

        before_status = problem.workflow_status
        before_auto = problem.dispose_automatically
        problem.customer_acknowledgement_action = customer_action
        update_fields = ['customer_acknowledgement_action']

        values = dict(problem.custom_values or {})
        if customer_action == CUSTOMER_ACTION_DISPOSE:
            values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_TO_BE_DISPOSED
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
        elif customer_action == CUSTOMER_ACTION_SHIP_BACK:
            values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_TO_BE_SHIPPED_BACK
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
        elif customer_action == CUSTOMER_ACTION_REQUESTED_INFORMATION:
            values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = CURRENT_WORKFLOW_DEFAULT
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO

        # The public tracking-link action is a real row modification. Record the
        # customer as the most recent modifier in every Recent Row Modifier
        # column so the audit field reflects the actual latest actor rather than
        # the last authenticated staff member who touched the row.
        if problem.table_id:
            for column in problem.table.columns.all():
                if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                    values[column.field_key] = 'Customer'

        problem.custom_values = values
        problem.current_workflow = str(values.get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY) or before_status)
        # There is no authenticated ALS user behind a public tracking-link
        # response. Clearing modified_by avoids exposing the previous staff user
        # as though they made this customer-originated change. A later staff save
        # sets modified_by and the Recent Row Modifier value back to that user.
        problem.modified_by = None
        update_fields.extend(['custom_values', 'current_workflow', 'modified_by', 'modified_at'])

        after_status = problem.workflow_status
        after_auto = problem.dispose_automatically
        update_fields.extend(problem.apply_acknowledgement_status_transition(
            before_status, previous_dispose_automatically=before_auto
        ))
        # The lifecycle helper may clear a previous customer action when automatic
        # disposal is switched off. This POST is itself the new explicit customer
        # action, so preserve the selection that was just submitted.
        problem.customer_acknowledgement_action = customer_action
        update_fields.append('customer_acknowledgement_action')
        problem.save(update_fields=list(dict.fromkeys(update_fields)))

        customer_saved_images = []
        customer_saved_attachments = []
        if customer_action == CUSTOMER_ACTION_REQUESTED_INFORMATION:
            for original_name, compressed_bytes, stored_name in prepared_customer_images:
                image = ProblemImage.objects.create(
                    problem=problem,
                    image=ContentFile(compressed_bytes, name=stored_name),
                    original_name=original_name,
                    uploaded_by=None,
                    include_in_customer_notification=True,
                )
                customer_saved_images.append({
                    'id': image.id,
                    'name': original_name,
                    'size_bytes': len(compressed_bytes),
                })

            for uploaded in customer_attachment_uploads:
                attachment = ProblemAttachment.objects.create(
                    problem=problem,
                    file=uploaded,
                    original_name=(uploaded.name or 'customer-attachment')[:255],
                    content_type=(getattr(uploaded, 'content_type', '') or '')[:160],
                    size_bytes=uploaded.size,
                    uploaded_by=None,
                    include_in_customer_notification=True,
                )
                customer_saved_attachments.append({
                    'id': attachment.id,
                    'name': attachment.original_name,
                    'size_bytes': attachment.size_bytes,
                    'content_type': attachment.content_type,
                })

            # _problem() prefetched these relations before the uploads existed.
            # Drop those caches so the response immediately includes the newly
            # uploaded customer files instead of requiring a page refresh.
            prefetched = getattr(problem, '_prefetched_objects_cache', {})
            prefetched.pop('images', None)
            prefetched.pop('attachments', None)

        label = {
            CUSTOMER_ACTION_DISPOSE: 'Permit immediate disposal',
            CUSTOMER_ACTION_SHIP_BACK: 'Ship back',
            CUSTOMER_ACTION_REQUESTED_INFORMATION: 'Give us more details about this ticket',
        }[customer_action]
        details = {
            'customer_action': customer_action,
            'customer_action_label': label,
            'customer_signature': customer_signature,
            'responded_via': 'public_tracking_link',
        }
        if customer_action == CUSTOMER_ACTION_REQUESTED_INFORMATION:
            details['customer_requested_information'] = requested_information
            if customer_saved_images:
                details['customer_uploaded_images'] = customer_saved_images
            if customer_saved_attachments:
                details['customer_uploaded_attachments'] = customer_saved_attachments
        changes = []
        if before_status != after_status:
            changes.append({'field': 'Current Workflow', 'before': before_status, 'after': after_status})
        if before_auto != after_auto:
            changes.append({
                'field': 'Dispose Automatically',
                'before': DISPOSE_AUTOMATICALLY_YES if before_auto else DISPOSE_AUTOMATICALLY_NO,
                'after': DISPOSE_AUTOMATICALLY_YES if after_auto else DISPOSE_AUTOMATICALLY_NO,
            })
        if changes:
            details['changes'] = changes
        ProblemHistory.objects.create(
            problem=problem,
            action=ProblemHistory.ACTION_UPDATED,
            actor=None,
            summary=f'Customer selected: {label}',
            details=details,
        )
        return Response(self._payload(problem))

class ProblemAcknowledgementImageView(APIView):
    """Serve a problem image only while its ticket tracking token is valid."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token, image_id):
        if not is_strong_tracking_token(token):
            return Response({'detail': 'Ticket tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
        problem = ProblemSample.objects.select_related('tracking_link_record').filter(tracking_link_record__tracking_token=token).first()
        if not problem or problem.tracking_link_expired:
            return Response({'detail': 'Ticket tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
        image = ProblemImage.objects.filter(pk=image_id, problem=problem).first()
        if not image or not image.image:
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        stored_filename = os.path.basename(image.image.name) or f'image-{image.id}'
        filename = stored_filename if stored_filename.lower().endswith('.webp') else (image.original_name or stored_filename)
        content_type = mimetypes.guess_type(stored_filename)[0] or 'application/octet-stream'
        try:
            image.image.open('rb')
        except (OSError, ValueError):
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(image.image, as_attachment=False, filename=filename, content_type=content_type)


class ProblemAcknowledgementAttachmentView(APIView):
    """Serve a problem attachment only while its ticket tracking token is valid."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token, attachment_id):
        if not is_strong_tracking_token(token):
            return Response({'detail': 'Ticket tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
        problem = ProblemSample.objects.select_related('tracking_link_record').filter(tracking_link_record__tracking_token=token).first()
        if not problem or problem.tracking_link_expired:
            return Response({'detail': 'Ticket tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
        attachment = ProblemAttachment.objects.filter(pk=attachment_id, problem=problem).first()
        if not attachment or not attachment.file:
            return Response({'detail': 'File not found.'}, status=status.HTTP_404_NOT_FOUND)
        filename = attachment.original_name or os.path.basename(attachment.file.name) or f'attachment-{attachment.id}'
        content_type = attachment.content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        try:
            attachment.file.open('rb')
        except (OSError, ValueError):
            return Response({'detail': 'File not found.'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(attachment.file, as_attachment=True, filename=filename, content_type=content_type)
