from datetime import timedelta
import uuid
from django.db import transaction
from django.db.models import Q, F
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, FileResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from email.message import EmailMessage
from email import policy
import mimetypes
import os
from PIL import Image as PillowImage, UnidentifiedImageError
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError
from accounts.models import UserProfile
from .models import ProblemSample, ProblemComment, ProblemImage, ProblemAttachment, ProblemTable, ProblemColumn, ProblemHistory, ProblemContainer, SYSTEM_PROBLEM_STATUSES, PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_AUTOMATICALLY_DISPOSED, PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL, PROBLEM_STATUS_TO_BE_SHIPPED_BACK, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING, PROBLEM_STATUS_BACK_TO_TESTING, PROBLEM_STATUS_SHIPPED_BACK, CUSTOMER_ACTION_DISPOSE, CUSTOMER_ACTION_SHIP_BACK, CUSTOMER_ACTION_HOLD, CUSTOMER_ACTION_REQUESTED_INFORMATION, generate_acknowledgement_token, SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY, SYSTEM_TRACKING_LINK_FIELD_KEY, SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY
from .serializers import (
    ProblemSampleSerializer, ShippingProblemSampleSerializer, CommentSerializer, ImageSerializer, AttachmentSerializer, ProblemTableSerializer, ProblemColumnSerializer, ProblemContainerSerializer,
)
from .search import search_problem_samples
from .advanced_search import advanced_search_problem_samples


MAX_ROW_FILE_BYTES = 25 * 1024 * 1024
MAX_NOTIFICATION_FILES_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP'}


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
    if problem.workflow_status != PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
        return 'Not automatic'
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
            'name': 'Problem ID', 'column_type': ProblemColumn.TYPE_NUMBER, 'required': True,
            'searchable': True, 'choices': [], 'default_value': None, 'position': 0, 'is_system': True,
        }
        for field, value in desired.items():
            if getattr(column, field) != value:
                setattr(column, field, value); changed.append(field)
        if changed:
            column.save(update_fields=changed + ['modified_at'])
        return column
    return ProblemColumn.objects.create(
        table=table, name='Problem ID', field_key='problem-id',
        column_type=ProblemColumn.TYPE_NUMBER, required=True, searchable=True,
        choices=[], default_value=None, position=0, is_system=True,
    )



def ensure_status_column(table):
    choices = list(SYSTEM_PROBLEM_STATUSES)
    column = table.columns.filter(field_key='status').first()
    if column is None:
        column = ProblemColumn.objects.create(
            table=table, name='Status', description='Current workflow status of the problem sample.',
            field_key='status', column_type=ProblemColumn.TYPE_CHOICE, required=True, searchable=True,
            include_in_customer_notification=False, choices=choices,
            default_value=PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL, position=1, is_system=True,
        )
    else:
        desired = {
            'name': 'Status', 'column_type': ProblemColumn.TYPE_CHOICE, 'required': True,
            'searchable': True, 'choices': choices, 'default_value': PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL,
            'position': 1, 'is_system': True,
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
        # Keep this computed built-in immediately after Status without disturbing
        # Problem ID (0) or Status (1). Existing user columns move one slot right.
        table.columns.filter(position__gte=2).update(position=F('position') + 1)
        column = ProblemColumn.objects.create(
            table=table,
            name='Days until up for disposal',
            description='Read-only countdown until this sample becomes automatically eligible for disposal. The countdown restarts whenever Status changes to Automatically Disposed and applies only while that status is active.',
            field_key=SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY,
            column_type=ProblemColumn.TYPE_NUMBER,
            required=False, searchable=True,
            include_in_customer_notification=False, choices=[], default_value=None,
            position=2, is_system=True,
        )
    else:
        desired = {
            'name': 'Days until up for disposal',
            'description': 'Read-only countdown until this sample becomes automatically eligible for disposal. The countdown restarts whenever Status changes to Automatically Disposed and applies only while that status is active.',
            'column_type': ProblemColumn.TYPE_NUMBER, 'required': False, 'searchable': True,
            'include_in_customer_notification': False, 'choices': [], 'default_value': None,
            'position': 2, 'is_system': True,
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

    # Positions 0..2 are Problem ID, Status, and Days until up for disposal.
    # Shift ordinary columns only when one or both tracking columns are missing.
    if link_column is None and expiry_column is None:
        table.columns.filter(position__gte=3).update(position=F('position') + 2)
    elif link_column is None:
        table.columns.filter(position__gte=3).exclude(pk=expiry_column.pk).update(position=F('position') + 1)
    elif expiry_column is None:
        table.columns.filter(position__gte=4).exclude(pk=link_column.pk).update(position=F('position') + 1)

    if link_column is None:
        link_column = ProblemColumn.objects.create(
            table=table, name='Tracking Link',
            description='Persistent secure Problem Sample Tracking Link for this row. At most one link exists per problem sample.',
            field_key=SYSTEM_TRACKING_LINK_FIELD_KEY, column_type=ProblemColumn.TYPE_URL,
            required=False, searchable=False, include_in_customer_notification=False,
            choices=[], default_value=None, position=3, is_system=True,
        )
    else:
        desired = {
            'name': 'Tracking Link',
            'description': 'Persistent secure Problem Sample Tracking Link for this row. At most one link exists per problem sample.',
            'column_type': ProblemColumn.TYPE_URL, 'required': False, 'searchable': False,
            'include_in_customer_notification': False, 'choices': [], 'default_value': None,
            'position': 3, 'is_system': True,
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
            description='When the tracking link becomes inaccessible. It resets to 30 days whenever Status switches to a disposal, shipping, or back-to-testing workflow state.',
            field_key=SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY, column_type=ProblemColumn.TYPE_DATETIME,
            required=False, searchable=False, include_in_customer_notification=False,
            choices=[], default_value=None, position=4, is_system=True,
        )
    else:
        desired = {
            'name': 'Tracking Link Expiry',
            'description': 'When the tracking link becomes inaccessible. It resets to 30 days whenever Status switches to a disposal, shipping, or back-to-testing workflow state.',
            'column_type': ProblemColumn.TYPE_DATETIME, 'required': False, 'searchable': False,
            'include_in_customer_notification': False, 'choices': [], 'default_value': None,
            'position': 4, 'is_system': True,
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
    ensure_status_column(table)
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
    table = ProblemTable.objects.create(name='Problem Samples', description='Default problem sample table', is_default=True)
    ensure_builtin_columns(table)
    return table


class ProblemSampleViewSet(viewsets.ModelViewSet):
    serializer_class = ProblemSampleSerializer

    def get_queryset(self):
        queryset = (ProblemSample.objects.select_related('created_by', 'modified_by', 'table', 'container')
                    .prefetch_related('comments', 'images__uploaded_by', 'attachments__uploaded_by', 'history__actor', 'table__columns')
                    .order_by('-problem_number'))
        table_id = self.request.query_params.get('table')
        if table_id:
            queryset = queryset.filter(table_id=table_id)
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
            lifecycle_fields = problem.apply_acknowledgement_status_transition('', changed_at=timezone.now())
            if lifecycle_fields:
                problem.save(update_fields=list(dict.fromkeys(lifecycle_fields)))
            ProblemHistory.objects.create(
                problem=problem, action=ProblemHistory.ACTION_CREATED, actor=self.request.user,
                summary='Created problem sample', details={},
            )

    def perform_update(self, serializer):
        reason = _change_reason(self.request)
        instance = serializer.instance
        before_custom = dict(instance.custom_values or {})
        before_core = {
            field: getattr(instance, field)
            for field in [
                'source_id', 'status', 'als_tracking_number', 'problem_sample_count', 'brand',
                'distributor', 'end_user', 'date_received', 'problem_type', 'issue_description',
                'client_contact_email', 'courier', 'courier_tracking_number', 'notify', 'email_confirmation',
            ]
        }
        before_status = str(before_custom.get('status') or before_core.get('status') or '').strip()
        before_container = instance.container.container_id if instance.container_id and instance.container else ''
        problem = serializer.save(modified_by=self.request.user)
        lifecycle_fields = problem.apply_acknowledgement_status_transition(before_status)
        if lifecycle_fields:
            problem.save(update_fields=list(dict.fromkeys(lifecycle_fields)))

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
            'source_id': 'Source ID', 'status': 'Status', 'als_tracking_number': 'ALS Tracking Number',
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

    @action(detail=False, methods=['get', 'post'], url_path='follow-up-required')
    def follow_up_required(self, request):
        # Follow Up Required is table-scoped.  The selected ProblemTable is the
        # source of truth for both searching and rendering; do not infer a table
        # from row values or from a collection of generic workflow fields.
        table_id = (request.data.get('table') if request.method.lower() == 'post' else request.query_params.get('table'))
        if not table_id:
            return Response({'detail': 'A problem sample table is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            table = ProblemTable.objects.prefetch_related('columns').get(pk=table_id)
        except (ProblemTable.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Problem sample table not found.'}, status=status.HTTP_404_NOT_FOUND)

        follow_up_statuses = {
            PROBLEM_STATUS_AUTOMATICALLY_DISPOSED,
            PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL,
        }
        queryset = (ProblemSample.objects.select_related('created_by', 'modified_by', 'table', 'container')
                    .prefetch_related('table__columns')
                    .filter(table=table))

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

        # workflow_status gives custom_values['status'] precedence over the legacy
        # status field.  Keep only the workflow states that genuinely require
        # follow-up, then force oldest-first even when a search returned a score
        # ranking so the longest-waiting matching row remains first.
        samples = [sample for sample in candidates if sample.workflow_status in follow_up_statuses]
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
                {'detail': 'Select at least one problem sample to dispose.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        problem_ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                problem_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return Response(
                    {'detail': f'Invalid problem sample ID: {raw_id}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if problem_id not in seen:
                seen.add(problem_id)
                problem_ids.append(problem_id)

        samples = list(
            ProblemSample.objects.select_for_update()
            .select_related('table', 'container')
            .prefetch_related('table__columns')
            .filter(pk__in=problem_ids)
        )
        by_id = {sample.id: sample for sample in samples}
        missing = [str(problem_id) for problem_id in problem_ids if problem_id not in by_id]
        if missing:
            return Response(
                {'detail': 'One or more selected problem samples no longer exist.', 'missing_ids': missing},
                status=status.HTTP_404_NOT_FOUND,
            )

        ordered_samples = [by_id[problem_id] for problem_id in problem_ids]
        already_disposed = [sample for sample in ordered_samples if sample.workflow_status == PROBLEM_STATUS_DISPOSED]
        if already_disposed:
            return Response(
                {
                    'detail': 'One or more selected problem samples are already Disposed. Refresh the search and try again.',
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
                    'detail': 'A selected problem sample belongs to a disposed container. Undo that container disposal before disposing the sample individually.',
                    'blocking_problem_ids': [sample.problem_number for sample in disposed_container_samples],
                },
                status=status.HTTP_409_CONFLICT,
            )

        now = timezone.now()
        modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
        changed = []
        for sample in ordered_samples:
            before = sample.workflow_status
            values = dict(sample.custom_values or {})
            values['status'] = PROBLEM_STATUS_DISPOSED
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier

            sample.custom_values = values
            sample.status = PROBLEM_STATUS_DISPOSED
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(before, changed_at=now)
            sample.save(update_fields=list(dict.fromkeys([
                'custom_values', 'status', 'modified_by', 'modified_at', *lifecycle_fields,
            ])))
            ProblemHistory.objects.create(
                problem=sample,
                action=ProblemHistory.ACTION_UPDATED,
                actor=request.user,
                summary='Disposed sample',
                details=_history_details({
                    'disposal_action': 'bulk_dispose_samples',
                    'changes': [{
                        'field': 'Status',
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
            Q(status=PROBLEM_STATUS_TO_BE_SHIPPED_BACK)
            | Q(custom_values__status=PROBLEM_STATUS_TO_BE_SHIPPED_BACK)
        )
        return Response(ShippingProblemSampleSerializer(queryset, many=True, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='to-be-back-to-testing')
    def to_be_back_to_testing(self, request):
        queryset = self.get_queryset().filter(
            Q(status=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
            | Q(custom_values__status=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)
        )
        return Response(ShippingProblemSampleSerializer(queryset, many=True, context={'request': request}).data)

    @action(detail=False, methods=['post'], url_path='bulk-back-to-testing')
    @transaction.atomic
    def bulk_back_to_testing(self, request):
        reason = _change_reason(request)
        raw_ids = request.data.get('problem_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'detail': 'Select at least one problem sample to return to testing.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        problem_ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                problem_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return Response(
                    {'detail': f'Invalid problem sample ID: {raw_id}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if problem_id not in seen:
                seen.add(problem_id)
                problem_ids.append(problem_id)

        samples = list(
            ProblemSample.objects.select_for_update()
            .select_related('table', 'container')
            .prefetch_related('table__columns')
            .filter(pk__in=problem_ids)
        )
        by_id = {sample.id: sample for sample in samples}
        missing = [str(problem_id) for problem_id in problem_ids if problem_id not in by_id]
        if missing:
            return Response(
                {'detail': 'One or more selected problem samples no longer exist.', 'missing_ids': missing},
                status=status.HTTP_404_NOT_FOUND,
            )

        ordered_samples = [by_id[problem_id] for problem_id in problem_ids]
        blocked = [sample for sample in ordered_samples if sample.workflow_status != PROBLEM_STATUS_TO_BE_BACK_TO_TESTING]
        if blocked:
            return Response(
                {
                    'detail': 'One or more selected problem samples are no longer To be back to testing. Refresh the Back To Testing page and try again.',
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
                    'detail': 'A selected problem sample belongs to a disposed container. Undo that container disposal before changing its testing status.',
                    'blocking_problem_ids': [sample.problem_number for sample in disposed_container_samples],
                },
                status=status.HTTP_409_CONFLICT,
            )

        now = timezone.now()
        modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
        changed = []
        for sample in ordered_samples:
            before = sample.workflow_status
            values = dict(sample.custom_values or {})
            values['status'] = PROBLEM_STATUS_BACK_TO_TESTING
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier

            sample.custom_values = values
            sample.status = PROBLEM_STATUS_BACK_TO_TESTING
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(before, changed_at=now)
            sample.save(update_fields=list(dict.fromkeys([
                'custom_values', 'status', 'modified_by', 'modified_at', *lifecycle_fields,
            ])))
            ProblemHistory.objects.create(
                problem=sample,
                action=ProblemHistory.ACTION_UPDATED,
                actor=request.user,
                summary='Back to testing',
                details=_history_details({
                    'testing_action': 'bulk_back_to_testing',
                    'changes': [{
                        'field': 'Status',
                        'before': before,
                        'after': PROBLEM_STATUS_BACK_TO_TESTING,
                    }],
                }, reason),
            )
            changed.append(sample)

        return Response({
            'count': len(changed),
            'problem_ids': [str(sample.id) for sample in changed],
            'problem_numbers': [sample.problem_number for sample in changed],
        })

    @action(detail=False, methods=['post'], url_path='bulk-ship-back')
    @transaction.atomic
    def bulk_ship_back(self, request):
        reason = _change_reason(request)
        raw_ids = request.data.get('problem_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'detail': 'Select at least one problem sample to ship.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        problem_ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                problem_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return Response(
                    {'detail': f'Invalid problem sample ID: {raw_id}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if problem_id not in seen:
                seen.add(problem_id)
                problem_ids.append(problem_id)

        samples = list(
            ProblemSample.objects.select_for_update()
            .select_related('table', 'container')
            .prefetch_related('table__columns')
            .filter(pk__in=problem_ids)
        )
        by_id = {sample.id: sample for sample in samples}
        missing = [str(problem_id) for problem_id in problem_ids if problem_id not in by_id]
        if missing:
            return Response(
                {'detail': 'One or more selected problem samples no longer exist.', 'missing_ids': missing},
                status=status.HTTP_404_NOT_FOUND,
            )

        ordered_samples = [by_id[problem_id] for problem_id in problem_ids]
        blocked = [sample for sample in ordered_samples if sample.workflow_status != PROBLEM_STATUS_TO_BE_SHIPPED_BACK]
        if blocked:
            return Response(
                {
                    'detail': 'One or more selected problem samples are no longer To be shipped back to client. Refresh the Shipping page and try again.',
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
                    'detail': 'A selected problem sample belongs to a disposed container. Undo that container disposal before changing its shipping status.',
                    'blocking_problem_ids': [sample.problem_number for sample in disposed_container_samples],
                },
                status=status.HTTP_409_CONFLICT,
            )

        now = timezone.now()
        modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
        changed = []
        for sample in ordered_samples:
            before = sample.workflow_status
            values = dict(sample.custom_values or {})
            values['status'] = PROBLEM_STATUS_SHIPPED_BACK
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier

            sample.custom_values = values
            sample.status = PROBLEM_STATUS_SHIPPED_BACK
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(before, changed_at=now)
            sample.save(update_fields=list(dict.fromkeys([
                'custom_values', 'status', 'modified_by', 'modified_at', *lifecycle_fields,
            ])))
            ProblemHistory.objects.create(
                problem=sample,
                action=ProblemHistory.ACTION_UPDATED,
                actor=request.user,
                summary='Shipped back to client',
                details=_history_details({
                    'shipping_action': 'bulk_ship_back',
                    'changes': [{
                        'field': 'Status',
                        'before': before,
                        'after': PROBLEM_STATUS_SHIPPED_BACK,
                    }],
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
            return Response({'detail': 'Problem sample table not found.'}, status=status.HTTP_404_NOT_FOUND)
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
        image = ProblemImage.objects.create(
            problem=problem,
            image=uploaded,
            original_name=(uploaded.name or 'image')[:255],
            uploaded_by=request.user,
            include_in_customer_notification=_request_bool(request.data.get('include_in_customer_notification'), True),
        )
        return Response(ImageSerializer(image, context={'request': request}).data, status=status.HTTP_201_CREATED)

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
    def customer_notification_credentials(self, request, pk=None):
        """Prepare a secure problem sample tracking link without persisting a new token.

        An existing token from a previously confirmed notification is reused.
        Otherwise the token exists only in this response until the user confirms
        the email was sent through customer-notification-sent.
        """
        problem = self.get_object()
        persisted = bool(problem.acknowledgement_token)
        token = problem.acknowledgement_token if persisted else generate_acknowledgement_token()
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

    @action(detail=True, methods=['post'], url_path='customer-notification-draft')
    def customer_notification_draft(self, request, pk=None):
        problem = self.get_object()
        to_recipients = _validated_email_list(request.data.get('to'))
        cc_recipients = _validated_email_list(request.data.get('cc'))
        subject = str(request.data.get('subject') or f'Problem Sample #{problem.problem_number}')[:500]
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
            filename = image.original_name or os.path.basename(image.image.name) or 'image'
            _add_message_file(message, image.image, filename)
        for attachment in attachments:
            filename = attachment.original_name or os.path.basename(attachment.file.name) or 'attachment'
            _add_message_file(message, attachment.file, filename, attachment.content_type)

        response = HttpResponse(message.as_bytes(), content_type='message/rfc822')
        response['Content-Disposition'] = f'attachment; filename="problem-sample-{problem.problem_number}-customer-notification.eml"'
        return response

    @action(detail=True, methods=['post'], url_path='customer-notification-sent')
    def customer_notification_sent(self, request, pk=None):
        problem = self.get_object()
        delivery_method = str(request.data.get('delivery_method') or '').strip().lower()
        if delivery_method not in {'mailto', 'eml'}:
            delivery_method = ''

        # A new problem sample tracking link does not exist in the database until this
        # explicit confirmation. The email preparation step returns a temporary token
        # to the browser only. Previously persisted tokens are reused on resends.
        supplied_token = str(request.data.get('tracking_token') or request.data.get('acknowledgement_token') or '').strip()
        stored_credentials = bool(problem.acknowledgement_token)
        credential_fields = []

        if stored_credentials:
            if supplied_token and supplied_token != str(problem.acknowledgement_token):
                return Response({'detail': 'The prepared problem sample tracking link is no longer current. Prepare the customer email again.'}, status=status.HTTP_409_CONFLICT)
        else:
            if not supplied_token:
                return Response({'detail': 'Prepare the customer notification before confirming that it was sent.'}, status=status.HTTP_400_BAD_REQUEST)
            # New problem sample tracking links use a 48-byte URL-safe random token
            # (64 URL characters / about 384 bits of entropy). Existing UUID
            # links remain valid after migration, but newly prepared links
            # must use the stronger token format.
            if len(supplied_token) != 64 or any(
                character not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
                for character in supplied_token
            ):
                return Response({'detail': 'Invalid problem sample tracking token.'}, status=status.HTTP_400_BAD_REQUEST)
            if ProblemSample.objects.filter(acknowledgement_token=supplied_token).exclude(pk=problem.pk).exists():
                return Response({'detail': 'The prepared problem sample tracking link conflicts with another problem sample. Prepare the customer email again.'}, status=status.HTTP_409_CONFLICT)
            problem.acknowledgement_token = supplied_token
            credential_fields.append('acknowledgement_token')

        # The first confirmed customer email activates automatic disposal by
        # changing Halted Automatic Disposal to Automatically Disposed. Entering that
        # status starts a fresh expiration period. Resends do not reset the period
        # unless the status actually transitions into Automatically Disposed again.
        first_notification = problem.customer_notified_at is None
        changes = []
        update_fields = list(credential_fields)

        if first_notification:
            now = timezone.now()
            before_status = problem.workflow_status
            before_disposal_days = _automatic_disposal_history_value(problem)
            problem.customer_notified_at = now
            update_fields.append('customer_notified_at')

            if before_status != PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
                values = dict(problem.custom_values or {})
                values['status'] = PROBLEM_STATUS_AUTOMATICALLY_DISPOSED
                problem.custom_values = values
                problem.status = PROBLEM_STATUS_AUTOMATICALLY_DISPOSED
                problem.modified_by = request.user
                update_fields.extend(['custom_values', 'status', 'modified_by'])
                update_fields.extend(problem.apply_acknowledgement_status_transition(before_status, changed_at=now))
                changes.append({
                    'field': 'Status',
                    'before': before_status,
                    'after': PROBLEM_STATUS_AUTOMATICALLY_DISPOSED,
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
            summary='Sent an email to the customer',
            details={
                'delivery_method': delivery_method,
                'confirmation': 'User confirmed the customer notification email was sent.',
                'starts_pt_clock': bool(first_notification and changes),
                'automatic_disposal_activated': bool(first_notification and changes),
                'acknowledgement_credentials_saved': bool(credential_fields),
                'changes': changes,
            },
        )
        problem.refresh_from_db(fields=['customer_notified_at', 'status', 'custom_values', 'modified_by'])
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

    @action(detail=True, methods=['post'])
    def comments(self, request, pk=None):
        problem = self.get_object()
        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'detail': 'Comment cannot be blank.'}, status=status.HTTP_400_BAD_REQUEST)
        comment = ProblemComment.objects.create(problem=problem, body=body, author=request.user)
        ProblemHistory.objects.create(
            problem=problem, action=ProblemHistory.ACTION_COMMENT, actor=request.user,
            summary='Added comment', details={'comment': body},
        )
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


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

    @action(detail=True, methods=['post'], url_path='dispose')
    @transaction.atomic
    def dispose(self, request, pk=None):
        container = ProblemContainer.objects.select_for_update().select_related('disposed_by').get(pk=pk)
        if container.disposed_at:
            return Response(self.get_serializer(container).data)
        reason = _change_reason(request)
        samples = list(container.problem_samples.select_related('table').prefetch_related('table__columns'))
        if not samples:
            return Response({'detail': 'An empty container cannot be disposed.'}, status=status.HTTP_409_CONFLICT)

        # Samples already shipped back or individually disposed are outside the
        # physical container disposal workload. They neither block readiness nor
        # get changed when the physical disposal container is disposed.
        disposal_samples = [
            sample for sample in samples
            if sample.workflow_status not in {PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_DISPOSED}
        ]
        if not disposal_samples:
            return Response({
                'detail': 'This container has no problem samples that require disposal. Samples already Disposed or Shipped back to client are ignored.',
            }, status=status.HTTP_409_CONFLICT)

        blocked = [sample for sample in disposal_samples if not sample.is_disposal_eligible]
        if blocked:
            return Response({
                'detail': 'This container is not ready to be disposed. Ignoring samples already Disposed or Shipped back to client, every remaining problem sample must be To be Disposed, or be Automatically Disposed and past its problem sample expiration period. Halted Automatic Disposal, To be shipped back to client, To be back to testing, and Back to testing are not automatically disposal-eligible.',
                'blocking_problem_ids': [sample.problem_number for sample in blocked],
            }, status=status.HTTP_409_CONFLICT)

        now = timezone.now()
        disposal_snapshot = {}
        for sample in disposal_samples:
            values = dict(sample.custom_values or {})
            before = str(values.get('status') or sample.status or '')
            disposal_snapshot[str(sample.id)] = {
                'status': sample.status,
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
            values['status'] = PROBLEM_STATUS_DISPOSED
            modifier = (getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or '').strip()
            if sample.table_id:
                for column in sample.table.columns.all():
                    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                        values[column.field_key] = modifier
            sample.custom_values = values
            sample.status = PROBLEM_STATUS_DISPOSED
            sample.modified_by = request.user
            lifecycle_fields = sample.apply_acknowledgement_status_transition(before, changed_at=now)
            sample.save(update_fields=list(dict.fromkeys(['custom_values', 'status', 'modified_by', 'modified_at'] + lifecycle_fields)))
            if before != PROBLEM_STATUS_DISPOSED:
                ProblemHistory.objects.create(
                    problem=sample, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
                    summary=f'Container {container.container_id} disposed',
                    details=_history_details({'changes': [{'field': 'Status', 'before': before or '—', 'after': PROBLEM_STATUS_DISPOSED}]}, reason),
                )

        container.disposed_at = now
        container.disposed_by = request.user
        container.disposal_snapshot = disposal_snapshot
        container.save(update_fields=['disposed_at', 'disposed_by', 'disposal_snapshot'])
        # Clear serializer cache if the object was reused.
        if hasattr(container, '_container_samples_cache'):
            delattr(container, '_container_samples_cache')
        return Response(self.get_serializer(container).data)

    @action(detail=True, methods=['post'], url_path='undo-disposal')
    @transaction.atomic
    def undo_disposal(self, request, pk=None):
        container = ProblemContainer.objects.select_for_update().select_related('disposed_by').get(pk=pk)
        if not container.disposed_at:
            return Response({'detail': 'This container has not been disposed.'}, status=status.HTTP_409_CONFLICT)

        reason = _change_reason(request)
        samples = list(container.problem_samples.select_related('table').prefetch_related('table__columns'))
        snapshot = container.disposal_snapshot or {}

        # New snapshots contain only samples actually changed by disposal. This
        # intentionally excludes Shipped back to client samples, which disposal
        # leaves untouched. For legacy empty snapshots, preserve the old check.
        if snapshot:
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
                before = str((saved.get('custom_values') or {}).get('status') or saved.get('status') or '')
                restore_plan.append((sample, before, saved))
                continue

            # Backward-compatible fallback for containers disposed before rollback snapshots existed.
            disposal_history = sample.history.filter(summary=history_summary).order_by('-created_at', '-id').first()
            before = ''
            if disposal_history:
                for change in (disposal_history.details or {}).get('changes', []):
                    if str(change.get('field') or '').strip().lower() == 'status':
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
                'detail': 'Container disposal cannot be undone because the previous status could not be recovered for every sample.',
                'blocking_problem_ids': missing,
            }, status=status.HTTP_409_CONFLICT)

        now = timezone.now()
        for sample, before, saved in restore_plan:
            if saved is not None:
                sample.custom_values = dict(saved.get('custom_values') or {})
                sample.status = str(saved.get('status') or '')
                sample.modified_by_id = saved.get('modified_by_id')
                sample.acknowledged_at = parse_datetime(saved.get('acknowledged_at')) if saved.get('acknowledged_at') else None
                if sample.workflow_status in {
                    PROBLEM_STATUS_AUTOMATICALLY_DISPOSED,
                    PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL,
                }:
                    # These statuses reactivate the persistent tracking link, so an
                    # old terminal-workflow expiry anchor must not be restored.
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
                elif sample.workflow_status == PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
                    # Legacy snapshots did not store this field. Treat restoration
                    # into Automatically Disposed as a fresh activation.
                    sample.automatic_disposal_started_at = now
                else:
                    sample.automatic_disposal_started_at = None
                update_fields = [
                    'custom_values', 'status', 'modified_by', 'modified_at',
                    'acknowledged_at', 'acknowledgement_status_changed_at', 'customer_acknowledgement_action',
                    'automatic_disposal_started_at',
                ]
            else:
                values = dict(sample.custom_values or {})
                values['status'] = before
                sample.custom_values = values
                sample.status = before
                sample.modified_by = request.user
                lifecycle_fields = sample.apply_acknowledgement_status_transition(
                    PROBLEM_STATUS_DISPOSED, changed_at=now
                )
                update_fields = list(dict.fromkeys(
                    ['custom_values', 'status', 'modified_by', 'modified_at'] + lifecycle_fields
                ))

            sample.save(update_fields=update_fields)
            ProblemHistory.objects.create(
                problem=sample, action=ProblemHistory.ACTION_UPDATED, actor=request.user,
                summary=f'Container {container.container_id} disposal undone',
                details=_history_details({'changes': [{'field': 'Status', 'before': PROBLEM_STATUS_DISPOSED, 'after': before or '—'}]}, reason),
            )

        container.disposed_at = None
        container.disposed_by = None
        container.disposal_snapshot = {}
        container.save(update_fields=['disposed_at', 'disposed_by', 'disposal_snapshot'])
        if hasattr(container, '_container_samples_cache'):
            delattr(container, '_container_samples_cache')
        return Response(self.get_serializer(container).data)


class ProblemTableViewSet(viewsets.ModelViewSet):
    queryset = ProblemTable.objects.prefetch_related('columns').select_related('created_by')
    serializer_class = ProblemTableSerializer

    def perform_create(self, serializer):
        table = serializer.save(created_by=self.request.user)
        ensure_builtin_columns(table)

    def destroy(self, request, *args, **kwargs):
        table = self.get_object()
        if table.is_default:
            return Response({'detail': 'The default table cannot be deleted.'}, status=status.HTTP_409_CONFLICT)
        if table.problem_samples.exists():
            return Response({'detail': 'This table contains problem samples. Remove or archive them before deleting the table.'}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)


class ProblemColumnViewSet(viewsets.ModelViewSet):
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

        default = column.default_value
        has_default = not (default is None or default == '' or default == [])
        if not has_default:
            return

        # Adding a column behaves like a Microsoft List column: the chosen
        # default immediately fills that column for rows already in the table.
        for problem in column.table.problem_samples.only('id', 'custom_values'):
            values = dict(problem.custom_values or {})
            values[column.field_key] = default
            ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)

    @transaction.atomic
    def perform_update(self, serializer):
        previous_type = serializer.instance.column_type
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

        if column.column_type == ProblemColumn.TYPE_DISTRIBUTOR:
            # Distributor values must still refer to a current customer record
            # whose CoyType is Distributor after a column is converted/edited.
            from customers.models import Customer
            from customers.normalization import customer_type_is
            valid_names = {
                customer.company_name.casefold()
                for customer in Customer.objects.filter(customer_type__icontains='distributor').only('company_name', 'customer_type')
                if customer.company_name and customer_type_is(customer.customer_type, 'Distributor')
            }
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                current = values.get(column.field_key)
                if current and str(current).strip().casefold() not in valid_names:
                    values[column.field_key] = column.default_value if column.default_value not in (None, '', []) else None
                    ProblemSample.objects.filter(pk=problem.pk).update(custom_values=values)

        if column.column_type == ProblemColumn.TYPE_END_USER:
            # End User values must still refer to a current customer record
            # whose CoyType is End User after a column is converted/edited.
            from customers.models import Customer
            from customers.normalization import customer_type_is
            valid_names = {
                customer.company_name.casefold()
                for customer in Customer.objects.filter(customer_type__icontains='end').only('company_name', 'customer_type')
                if customer.company_name and customer_type_is(customer.customer_type, 'End User')
            }
            for problem in column.table.problem_samples.only('id', 'custom_values'):
                values = dict(problem.custom_values or {})
                current = values.get(column.field_key)
                if current and str(current).strip().casefold() not in valid_names:
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

    def get_queryset(self):
        queryset = super().get_queryset()
        table_id = self.request.query_params.get('table')
        if table_id:
            queryset = queryset.filter(table_id=table_id)
        return queryset

    def destroy(self, request, *args, **kwargs):
        column = self.get_object()
        if column.is_system:
            return Response({'detail': 'Built-in columns cannot be deleted.'}, status=status.HTTP_409_CONFLICT)
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
    """Public, tokenized problem sample tracking page API. No ALS account is required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def _problem(self, token):
        return (ProblemSample.objects.select_related('table')
                .prefetch_related('images', 'attachments', 'table__columns')
                .filter(acknowledgement_token=token).order_by('created_at').first())

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
        # This matters because Automatically Disposed uses a different set of
        # customer-facing labels for the same underlying workflow actions.
        for entry in problem.history.all()[:25]:
            details = entry.details if isinstance(entry.details, dict) else {}
            if details.get('customer_action') == action and details.get('customer_action_label'):
                return str(details['customer_action_label'])

        return {
            CUSTOMER_ACTION_DISPOSE: 'Dispose Sample(s)',
            CUSTOMER_ACTION_SHIP_BACK: 'Ship back samples',
            CUSTOMER_ACTION_HOLD: 'Hold sample',
            CUSTOMER_ACTION_REQUESTED_INFORMATION: 'Fill out requested information (if applicable)',
        }.get(action, '')

    def _payload(self, problem):
        workflow_status = problem.workflow_status
        visible_until = problem.tracking_link_expires_at
        public_files = self._public_files(problem)
        public_details = {'details': self._public_details(problem)}

        # Customer acknowledgement is tracked independently from workflow Status.
        # Halted Automatic Disposal is the default for new rows, so a halted row
        # with no acknowledged_at timestamp must still show the unresolved customer-action choices.
        if workflow_status in {PROBLEM_STATUS_AUTOMATICALLY_DISPOSED, PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL} and not problem.acknowledged_at:
            if workflow_status == PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
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
                    **public_details,
                **public_files,
                }
            return {
                'state': 'pending',
                'message': 'Please choose how ALS should handle this problem sample',
                'problem_number': problem.problem_number,
                'automatic_disposal_active': False,
                **public_details,
                **public_files,
            }

        if workflow_status == PROBLEM_STATUS_TO_BE_BACK_TO_TESTING:
            return {
                'state': 'testing',
                'message': 'Sample(s) marked to go back to testing',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
            }
        if workflow_status == PROBLEM_STATUS_BACK_TO_TESTING:
            return {
                'state': 'testing',
                'message': 'Back to testing',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
            }
        if workflow_status == PROBLEM_STATUS_DISPOSED:
            return {
                'state': 'dumped',
                'message': 'Problem Sample Dumped',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
            }
        if workflow_status in {PROBLEM_STATUS_TO_BE_SHIPPED_BACK, PROBLEM_STATUS_SHIPPED_BACK}:
            return {
                'state': 'shipping',
                'message': 'Shipping samples back to client',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
                'customer_action': problem.customer_acknowledgement_action or CUSTOMER_ACTION_SHIP_BACK,
                'customer_action_label': self._customer_action_label(problem) or 'Ship back',
            }
        if workflow_status == PROBLEM_STATUS_TO_BE_DISPOSED:
            return {
                'state': 'disposing',
                'message': 'Sample(s) marked for disposal',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'visible_until': visible_until,
                'customer_action': problem.customer_acknowledgement_action or '',
                'customer_action_label': self._customer_action_label(problem),
            }
        if workflow_status == PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL:
            return {
                'state': 'pending',
                'message': 'Please choose how ALS should handle this problem sample',
                'problem_number': problem.problem_number,
                **public_details,
                **public_files,
                'acknowledged_at': problem.acknowledged_at,
                'visible_until': visible_until,
                'customer_action': problem.customer_acknowledgement_action or '',
                'customer_action_label': self._customer_action_label(problem),
                'can_choose_action': True,
                'automatic_disposal_active': False,
            }

        return {
            'state': 'pending',
            'message': 'Please choose how ALS should handle this problem sample',
            'problem_number': problem.problem_number,
            **public_details,
            **public_files,
        }

    def get(self, request, token):
        problem = self._problem(token)
        if not problem or self._is_link_gone(problem):
            return Response({'detail': 'Problem sample tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._payload(problem))

    @transaction.atomic
    def post(self, request, token):
        problem = self._problem(token)
        if not problem or self._is_link_gone(problem):
            return Response({'detail': 'Problem sample tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)

        workflow_status = problem.workflow_status
        started_in_automatic_disposal = workflow_status == PROBLEM_STATUS_AUTOMATICALLY_DISPOSED
        # Only the pre-response workflow states accept a customer choice. Completed
        # or already-routed samples simply return their current public state.
        if workflow_status not in {PROBLEM_STATUS_AUTOMATICALLY_DISPOSED, PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL}:
            return Response(self._payload(problem))

        customer_action = str(request.data.get('action') or '').strip()
        customer_signature = ' '.join(str(request.data.get('signature') or '').split())
        if not customer_signature:
            return Response({'detail': 'Type your name as a signature before sending a response.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(customer_signature) > 200:
            return Response({'detail': 'Signature must be 200 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        if started_in_automatic_disposal:
            allowed_actions = {
                CUSTOMER_ACTION_DISPOSE,
                CUSTOMER_ACTION_SHIP_BACK,
                CUSTOMER_ACTION_HOLD,
                CUSTOMER_ACTION_REQUESTED_INFORMATION,
            }
        else:
            allowed_actions = {
                CUSTOMER_ACTION_DISPOSE,
                CUSTOMER_ACTION_SHIP_BACK,
                CUSTOMER_ACTION_REQUESTED_INFORMATION,
            }
        if customer_action not in allowed_actions:
            return Response({'detail': 'Choose a valid sample action.'}, status=status.HTTP_400_BAD_REQUEST)

        requested_information = str(request.data.get('requested_information') or '').strip()
        if customer_action == CUSTOMER_ACTION_REQUESTED_INFORMATION:
            if not requested_information:
                return Response({'detail': 'Enter the requested information before sending this response.'}, status=status.HTTP_400_BAD_REQUEST)
            if len(requested_information) > 4000:
                return Response({'detail': 'Requested information must be 4000 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        # There is no separate acknowledgement button. The first explicit customer
        # disposition choice both acknowledges receipt and records the requested action.
        # This keeps passive email-link previews/GET requests from acknowledging a row.
        if not problem.acknowledged_at:
            now = timezone.now()
            before_status = workflow_status
            values = dict(problem.custom_values or {})
            values['status'] = PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL
            problem.custom_values = values
            problem.status = PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL
            problem.acknowledged_at = now
            problem.customer_acknowledgement_action = ''
            update_fields = [
                'custom_values', 'status', 'acknowledged_at',
                'customer_acknowledgement_action',
            ]
            update_fields.extend(problem.apply_acknowledgement_status_transition(before_status, changed_at=now))
            problem.save(update_fields=list(dict.fromkeys(update_fields)))

            after_status = problem.workflow_status
            changes = []
            if before_status != after_status:
                changes.append({
                    'field': 'Status',
                    'before': before_status,
                    'after': after_status,
                })
            ProblemHistory.objects.create(
                problem=problem,
                action=ProblemHistory.ACTION_ACKNOWLEDGED,
                actor=None,
                summary='Customer acknowledged problem sample',
                details={
                    'acknowledged_via': 'public_tracking_link',
                    'changes': changes,
                },
            )

        # The tracking link reflects the row's current workflow state. A customer may
        # make a new choice whenever the row is back in an active follow-up state.

        before_status = problem.workflow_status
        problem.customer_acknowledgement_action = customer_action
        update_fields = ['customer_acknowledgement_action']

        values = dict(problem.custom_values or {})
        if customer_action == CUSTOMER_ACTION_DISPOSE:
            values['status'] = PROBLEM_STATUS_TO_BE_DISPOSED
            problem.status = PROBLEM_STATUS_TO_BE_DISPOSED
        elif customer_action == CUSTOMER_ACTION_SHIP_BACK:
            values['status'] = PROBLEM_STATUS_TO_BE_SHIPPED_BACK
            problem.status = PROBLEM_STATUS_TO_BE_SHIPPED_BACK
        elif customer_action == CUSTOMER_ACTION_REQUESTED_INFORMATION:
            values['status'] = PROBLEM_STATUS_TO_BE_BACK_TO_TESTING
            problem.status = PROBLEM_STATUS_TO_BE_BACK_TO_TESTING
        else:
            values['status'] = PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL
            problem.status = PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL

        problem.custom_values = values
        update_fields.extend(['custom_values', 'status'])

        after_status = problem.workflow_status
        if before_status != after_status:
            update_fields.extend(problem.apply_acknowledgement_status_transition(before_status))
        problem.save(update_fields=list(dict.fromkeys(update_fields)))

        if started_in_automatic_disposal:
            label = {
                CUSTOMER_ACTION_DISPOSE: 'Permit immediate disposal',
                CUSTOMER_ACTION_SHIP_BACK: 'Ship back',
                CUSTOMER_ACTION_HOLD: 'Stop eventual disposal',
                CUSTOMER_ACTION_REQUESTED_INFORMATION: 'Fill out requested information (if applicable)',
            }[customer_action]
        else:
            label = {
                CUSTOMER_ACTION_DISPOSE: 'Permit immediate disposal',
                CUSTOMER_ACTION_SHIP_BACK: 'Ship back',
                CUSTOMER_ACTION_HOLD: 'Hold sample',
                CUSTOMER_ACTION_REQUESTED_INFORMATION: 'Fill out requested information (if applicable)',
            }[customer_action]
        details = {
            'customer_action': customer_action,
            'customer_action_label': label,
            'customer_signature': customer_signature,
            'responded_via': 'public_tracking_link',
        }
        if customer_action == CUSTOMER_ACTION_REQUESTED_INFORMATION:
            details['customer_requested_information'] = requested_information
        if before_status != after_status:
            details['changes'] = [{'field': 'Status', 'before': before_status, 'after': after_status}]
        ProblemHistory.objects.create(
            problem=problem,
            action=ProblemHistory.ACTION_UPDATED,
            actor=None,
            summary=f'Customer selected: {label}',
            details=details,
        )
        return Response(self._payload(problem))

class ProblemAcknowledgementImageView(APIView):
    """Serve a problem image only while its problem sample tracking token is valid."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token, image_id):
        problem = ProblemSample.objects.filter(acknowledgement_token=token).first()
        if not problem or problem.tracking_link_expired:
            return Response({'detail': 'Problem sample tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
        image = ProblemImage.objects.filter(pk=image_id, problem=problem).first()
        if not image or not image.image:
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        filename = image.original_name or os.path.basename(image.image.name) or f'image-{image.id}'
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        try:
            image.image.open('rb')
        except (OSError, ValueError):
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(image.image, as_attachment=False, filename=filename, content_type=content_type)


class ProblemAcknowledgementAttachmentView(APIView):
    """Serve a problem attachment only while its problem sample tracking token is valid."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token, attachment_id):
        problem = ProblemSample.objects.filter(acknowledgement_token=token).first()
        if not problem or problem.tracking_link_expired:
            return Response({'detail': 'Problem sample tracking link not found.'}, status=status.HTTP_404_NOT_FOUND)
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

