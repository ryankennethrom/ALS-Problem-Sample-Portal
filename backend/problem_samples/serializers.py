import re
import copy
import math
from types import SimpleNamespace
from django.core.validators import validate_email, URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from django.utils import timezone
from django.conf import settings
from django.utils.text import slugify
from rest_framework import serializers
from accounts.models import UserProfile
from .models import ProblemSample, ProblemComment, ProblemImage, ProblemAttachment, ProblemTable, ProblemColumn, ProblemHistory, ProblemContainer, PROBLEM_STATUS_AUTOMATICALLY_DISPOSED, PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL, PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_DISPOSED, SYSTEM_TRACKING_LINK_FIELD_KEY, SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY


class ProblemColumnSerializer(serializers.ModelSerializer):
    column_type_label = serializers.CharField(source='get_column_type_display', read_only=True)
    group_users = serializers.SerializerMethodField()
    depends_on_column_name = serializers.SerializerMethodField()
    depends_on_field_key = serializers.SerializerMethodField()
    client_email_dependency_details = serializers.SerializerMethodField()

    class Meta:
        model = ProblemColumn
        fields = [
            'id', 'table', 'name', 'description', 'field_key', 'column_type', 'column_type_label',
            'required', 'searchable', 'include_in_customer_notification', 'choices', 'default_value', 'group_role', 'group_users',
            'depends_on_column', 'depends_on_column_name', 'depends_on_field_key',
            'client_email_dependencies', 'client_email_dependency_details', 'position', 'is_system',
            'created_at', 'modified_at',
        ]
        read_only_fields = ['field_key', 'is_system', 'group_users', 'depends_on_column_name', 'depends_on_field_key', 'client_email_dependency_details', 'created_at', 'modified_at']

    def get_depends_on_column_name(self, obj):
        return obj.depends_on_column.name if obj.depends_on_column else ''

    def get_depends_on_field_key(self, obj):
        return obj.depends_on_column.field_key if obj.depends_on_column else ''

    def get_client_email_dependency_details(self, obj):
        return [
            {
                'id': str(column.id),
                'name': column.name,
                'field_key': column.field_key,
                'column_type': column.column_type,
                'column_type_label': column.get_column_type_display(),
            }
            for column in obj.ordered_client_email_dependency_columns()
        ]

    def get_group_users(self, obj):
        if obj.column_type != ProblemColumn.TYPE_GROUP or not obj.group_role:
            return []
        profiles = (UserProfile.objects.filter(role=obj.group_role, user__is_active=True)
                    .select_related('user').order_by('user__email'))
        return [
            {
                'id': profile.user_id,
                'email': profile.user.email or profile.user.username,
                'name': profile.user.get_full_name() or profile.user.email or profile.user.username,
                'role': profile.role,
                'role_label': profile.get_role_display(),
            }
            for profile in profiles
        ]

    def validate(self, attrs):
        if self.instance and self.instance.is_system:
            raise serializers.ValidationError('Built-in columns cannot be edited.')
        proposed_name = attrs.get('name', getattr(self.instance, 'name', ''))
        reserved = slugify(proposed_name)
        if reserved == 'problem-id':
            raise serializers.ValidationError({'name': 'Problem ID is reserved as a built-in column.'})
        if reserved in {
            'days-until-up-for-disposal',
            'days-until-automatic-disposal',
            'system-days-until-automatic-disposal',
        }:
            raise serializers.ValidationError({'name': 'Days until up for disposal is reserved as a built-in column.'})
        if reserved in {'tracking-link', 'system-tracking-link'}:
            raise serializers.ValidationError({'name': 'Tracking Link is reserved as a built-in column.'})
        if reserved in {'tracking-link-expiry', 'system-tracking-link-expiry'}:
            raise serializers.ValidationError({'name': 'Tracking Link Expiry is reserved as a built-in column.'})
        column_type = attrs.get('column_type', getattr(self.instance, 'column_type', ProblemColumn.TYPE_TEXT))
        group_role = attrs.get('group_role', getattr(self.instance, 'group_role', ''))
        table = attrs.get('table', getattr(self.instance, 'table', None))
        depends_on_column = attrs.get('depends_on_column', getattr(self.instance, 'depends_on_column', None))
        dependency_ids = attrs.get(
            'client_email_dependencies',
            getattr(self.instance, 'client_email_dependencies', []) if self.instance else [],
        ) or []

        if column_type == ProblemColumn.TYPE_CLIENT_EMAIL:
            # Backward compatibility: a legacy single dependency becomes priority #1.
            if 'client_email_dependencies' not in attrs and depends_on_column:
                dependency_ids = [str(depends_on_column.pk)]
            if not isinstance(dependency_ids, list):
                raise serializers.ValidationError({'client_email_dependencies': 'Dependencies must be an ordered list of column IDs.'})

            cleaned_ids = []
            seen = set()
            dependency_columns = []
            for raw_id in dependency_ids:
                column_id = str(raw_id or '').strip()
                if not column_id or column_id in seen:
                    continue
                candidate = table.columns.filter(pk=column_id).first() if table else None
                if not candidate:
                    raise serializers.ValidationError({'client_email_dependencies': f'Unknown dependency column: {column_id}.'})
                if self.instance and candidate.pk == self.instance.pk:
                    raise serializers.ValidationError({'client_email_dependencies': 'A Client Email column cannot depend on itself.'})
                if candidate.is_system:
                    raise serializers.ValidationError({'client_email_dependencies': 'Choose user-defined fields as Client Email dependencies.'})
                allowed_dependency_types = {
                    ProblemColumn.TYPE_DISTRIBUTOR, ProblemColumn.TYPE_END_USER,
                    ProblemColumn.TYPE_TEXT, ProblemColumn.TYPE_FIXED,
                }
                if candidate.column_type not in allowed_dependency_types:
                    raise serializers.ValidationError({
                        'client_email_dependencies':
                            f'{candidate.name} cannot be used as a company dependency. Use Distributor, End User, text, or Fixed Value.'
                    })
                cleaned_ids.append(column_id)
                dependency_columns.append(candidate)
                seen.add(column_id)

            attrs['client_email_dependencies'] = cleaned_ids
            # Keep the legacy FK synchronized with priority #1 for old clients/data.
            attrs['depends_on_column'] = dependency_columns[0] if dependency_columns else None
            depends_on_column = attrs['depends_on_column']
        else:
            attrs['client_email_dependencies'] = []
            attrs['depends_on_column'] = None
            dependency_columns = []
            depends_on_column = None

        if column_type == ProblemColumn.TYPE_GROUP:
            if group_role not in {ProblemColumn.GROUP_LAB_TECHNICIAN, ProblemColumn.GROUP_CUSTOMER_SERVICE}:
                raise serializers.ValidationError({'group_role': 'Choose either Lab Technician or Customer Service.'})
            attrs['group_role'] = group_role
        else:
            attrs['group_role'] = ''

        choices = attrs.get('choices', getattr(self.instance, 'choices', [])) or []
        if column_type in {ProblemColumn.TYPE_CHOICE, ProblemColumn.TYPE_MULTI_CHOICE}:
            if not isinstance(choices, list) or not all(isinstance(x, str) and x.strip() for x in choices):
                raise serializers.ValidationError({'choices': 'Choice columns require a list of non-empty text options.'})
            cleaned = []
            seen = set()
            for item in choices:
                value = item.strip()
                if value.lower() not in seen:
                    cleaned.append(value)
                    seen.add(value.lower())
            attrs['choices'] = cleaned
        else:
            attrs['choices'] = []

        # Fixed Value, Row Creator, and Recent Row Modifier columns are read-only
        # on individual rows. The two user-audit types are populated by the server.
        # Historical imported rows may not have user metadata, so they are not required.
        if column_type == ProblemColumn.TYPE_FIXED:
            attrs['required'] = True
        elif column_type in {ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER}:
            attrs['required'] = False
            attrs['default_value'] = None

        # Keep the column default compatible with its configured type. The same
        # validator is used for row values so defaults cannot introduce data that
        # the row serializer would later reject.
        default_value = attrs.get('default_value', getattr(self.instance, 'default_value', None))
        if column_type in {ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER}:
            default_value = None
        if column_type == ProblemColumn.TYPE_CLIENT_EMAIL and dependency_columns and default_value not in (None, '', []):
            raise serializers.ValidationError({
                'default_value': 'A Client Email column with dependencies cannot have one table-wide default email.'
            })
        if default_value is None or default_value == '' or default_value == []:
            attrs['default_value'] = None
        else:
            try:
                attrs['default_value'] = _validate_custom_value(
                    SimpleNamespace(
                        column_type=column_type, choices=attrs.get('choices', []),
                        group_role=attrs.get('group_role', ''), depends_on_column=depends_on_column,
                        client_email_dependencies=attrs.get('client_email_dependencies', []), table=table,
                    ),
                    default_value,
                )
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({'default_value': exc.detail})

        if column_type == ProblemColumn.TYPE_FIXED and attrs.get('default_value') is None:
            raise serializers.ValidationError({'default_value': 'A Fixed Value column requires a fixed value.'})

        # A required column added to a table that already has rows needs a
        # default so those existing rows remain valid after the column is added.
        required = attrs.get('required', getattr(self.instance, 'required', False))
        if (self.instance is None and table and required and table.problem_samples.exists()
                and attrs.get('default_value') is None
                and column_type not in {ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER}):
            if column_type == ProblemColumn.TYPE_CLIENT_EMAIL and dependency_columns:
                raise serializers.ValidationError({
                    'required': 'Add a dependent Client Email column as optional first, populate existing rows, then mark it required.'
                })
            raise serializers.ValidationError({
                'default_value': 'A default value is required when adding a required column to a table that already contains rows.'
            })
        if (self.instance is not None and column_type == ProblemColumn.TYPE_GROUP and table and required
                and table.problem_samples.exists() and group_role != self.instance.group_role
                and attrs.get('default_value') is None):
            raise serializers.ValidationError({
                'default_value': 'Choose a default user before changing the group on a required column that already contains rows.'
            })
        return attrs

    def create(self, validated_data):
        table = validated_data['table']
        base = slugify(validated_data['name']) or 'column'
        base = re.sub(r'[^a-z0-9_-]', '', base)[:150] or 'column'
        key = base
        suffix = 2
        while ProblemColumn.objects.filter(table=table, field_key=key).exists():
            key = f'{base}-{suffix}'
            suffix += 1
        validated_data['field_key'] = key
        if 'position' not in validated_data:
            last = table.columns.order_by('-position').values_list('position', flat=True).first()
            validated_data['position'] = (last or 0) + 1
        return super().create(validated_data)


class ProblemTableSerializer(serializers.ModelSerializer):
    columns = ProblemColumnSerializer(many=True, read_only=True)
    row_count = serializers.IntegerField(source='problem_samples.count', read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = ProblemTable
        fields = [
            'id', 'name', 'description', 'pt_days', 'acknowledgement_link_days', 'is_default', 'columns', 'row_count',
            'created_by_email', 'created_at', 'modified_at',
        ]
        read_only_fields = ['acknowledgement_link_days', 'is_default', 'created_by_email', 'created_at', 'modified_at']


class CommentSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='author.email', read_only=True)

    class Meta:
        model = ProblemComment
        fields = ['id', 'body', 'author_email', 'legacy_author', 'created_at']


class ImageSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)
    size_bytes = serializers.SerializerMethodField()

    class Meta:
        model = ProblemImage
        fields = ['id', 'image', 'original_name', 'size_bytes', 'include_in_customer_notification', 'uploaded_by_email', 'uploaded_at']

    def get_size_bytes(self, obj):
        try:
            return obj.image.size if obj.image else 0
        except (OSError, ValueError):
            return 0


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)

    class Meta:
        model = ProblemAttachment
        fields = ['id', 'file', 'original_name', 'content_type', 'size_bytes', 'include_in_customer_notification', 'uploaded_by_email', 'uploaded_at']


class HistorySerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)
    actor_name = serializers.SerializerMethodField()
    action_label = serializers.CharField(source='get_action_display', read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = ProblemHistory
        fields = ['id', 'action', 'action_label', 'summary', 'details', 'actor_email', 'actor_name', 'created_at']

    def get_summary(self, obj):
        if obj.action == ProblemHistory.ACTION_CUSTOMER_NOTIFICATION:
            return 'Sent an email to the customer'
        if obj.action == ProblemHistory.ACTION_ACKNOWLEDGED:
            return 'Customer acknowledged problem sample'
        return obj.summary

    def get_actor_name(self, obj):
        if not obj.actor:
            details = obj.details or {}
            if (
                obj.action == ProblemHistory.ACTION_ACKNOWLEDGED
                or details.get('acknowledged_via') == 'public_verification_link'
                or details.get('responded_via') == 'public_acknowledgement_link'
                or details.get('responded_via') == 'public_tracking_link'
                or details.get('acknowledged_via') == 'public_tracking_link'
            ):
                return 'Customer'
            return ''
        return obj.actor.get_full_name() or obj.actor.email or obj.actor.username


class ProblemContainerSerializer(serializers.ModelSerializer):
    container_id = serializers.CharField(read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    sample_count = serializers.SerializerMethodField()
    expired_count = serializers.SerializerMethodField()
    active_count = serializers.SerializerMethodField()
    unnotified_count = serializers.SerializerMethodField()
    all_expired = serializers.SerializerMethodField()
    ready_to_dispose = serializers.SerializerMethodField()
    disposed_by_email = serializers.EmailField(source='disposed_by.email', read_only=True)
    status = serializers.SerializerMethodField()
    samples = serializers.SerializerMethodField()

    class Meta:
        model = ProblemContainer
        fields = [
            'id', 'container_id', 'sample_count', 'expired_count', 'active_count',
            'unnotified_count', 'all_expired', 'ready_to_dispose', 'status', 'samples',
            'created_by_email', 'created_at', 'disposed_at', 'disposed_by_email',
        ]
        read_only_fields = fields

    def _samples(self, obj):
        cache_name = '_container_samples_cache'
        if not hasattr(obj, cache_name):
            prefetched = getattr(obj, '_prefetched_objects_cache', {}).get('problem_samples')
            if prefetched is not None:
                samples = sorted(prefetched, key=lambda sample: sample.created_at, reverse=True)
            else:
                samples = list(obj.problem_samples.select_related('table').order_by('-created_at'))
            setattr(obj, cache_name, samples)
        return getattr(obj, cache_name)

    def get_sample_count(self, obj):
        return len(self._samples(obj))

    def get_expired_count(self, obj):
        return sum(1 for sample in self._samples(obj) if sample.expiration_status == 'expired')

    def get_active_count(self, obj):
        return sum(1 for sample in self._samples(obj) if sample.expiration_status == 'active')

    def get_unnotified_count(self, obj):
        return sum(1 for sample in self._samples(obj) if sample.expiration_status == 'not_notified')

    def get_all_expired(self, obj):
        samples = self._samples(obj)
        return bool(samples) and all(sample.expiration_status == 'expired' for sample in samples)

    def _sample_ready_for_disposal(self, sample):
        return sample.is_disposal_eligible

    def _disposal_samples(self, obj):
        # Samples already shipped back or individually disposed are no longer
        # part of the physical container disposal workload.
        return [
            sample for sample in self._samples(obj)
            if sample.workflow_status not in {PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_DISPOSED}
        ]

    def get_ready_to_dispose(self, obj):
        samples = self._disposal_samples(obj)
        return bool(samples) and all(self._sample_ready_for_disposal(sample) for sample in samples)

    def get_status(self, obj):
        if obj.disposed_at:
            return 'disposed'
        all_samples = self._samples(obj)
        if not all_samples:
            return 'empty'
        samples = self._disposal_samples(obj)
        if not samples:
            return 'active'
        if all(self._sample_ready_for_disposal(sample) for sample in samples):
            return 'ready_to_dispose'
        if any(self._sample_ready_for_disposal(sample) for sample in samples):
            return 'partially_ready'
        return 'active'

    def get_samples(self, obj):
        result = []
        now = timezone.now()
        for sample in self._samples(obj):
            expires_at = sample.expires_at
            days_remaining = None
            if expires_at is not None:
                days_remaining = max(0, math.ceil((expires_at - now).total_seconds() / 86400))
            result.append({
                'id': str(sample.id),
                'problem_number': sample.problem_number,
                'table_id': str(sample.table_id) if sample.table_id else '',
                'table_name': sample.table.name if sample.table_id else '',
                'pt_days': sample.table.pt_days if sample.table_id else None,
                'customer_notified_at': sample.customer_notified_at,
                'expires_at': expires_at,
                'expiration_status': sample.expiration_status,
                'status': str((sample.custom_values or {}).get('status') or sample.status or ''),
                'ready_for_disposal': self._sample_ready_for_disposal(sample),
                'days_until_expiration': days_remaining,
            })
        return result


def _is_empty(value):
    return value is None or value == '' or value == []


def _client_email_dependency_columns(column):
    if hasattr(column, 'ordered_client_email_dependency_columns'):
        return column.ordered_client_email_dependency_columns()
    # Lightweight objects used while validating defaults may not be model instances.
    table = getattr(column, 'table', None)
    raw_ids = [str(value) for value in (getattr(column, 'client_email_dependencies', []) or []) if value]
    legacy = getattr(column, 'depends_on_column', None)
    if not raw_ids and legacy is not None:
        return [legacy]
    if not table or not raw_ids:
        return []
    by_id = {str(item.id): item for item in table.columns.filter(id__in=raw_ids)}
    return [by_id[item_id] for item_id in raw_ids if item_id in by_id]


def _active_client_email_company(column, row_values):
    """Choose the first populated dependency whose company has at least one email."""
    from customers.models import Customer
    dependencies = _client_email_dependency_columns(column)
    populated = []
    for dependency in dependencies:
        company = str((row_values or {}).get(dependency.field_key) or '').strip()
        if not company:
            continue
        populated.append((dependency, company))
        if Customer.objects.filter(company_name__iexact=company).exclude(email='').exists():
            return dependency, company, populated
    return None, '', populated


def _validate_custom_value(column, value):
    if _is_empty(value):
        return value

    kind = column.column_type
    if kind in {ProblemColumn.TYPE_TEXT, ProblemColumn.TYPE_LONG_TEXT, ProblemColumn.TYPE_FIXED, ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER}:
        if not isinstance(value, str):
            raise serializers.ValidationError('Must be text.')
        return value
    if kind == ProblemColumn.TYPE_GROUP:
        if not isinstance(value, str) or '@' not in value:
            raise serializers.ValidationError('Select a user from the configured group.')
        email = value.strip().lower()
        profile = (UserProfile.objects.filter(
            role=getattr(column, 'group_role', ''),
            user__is_active=True,
            user__email__iexact=email,
        ).select_related('user').first())
        if not profile:
            group_label = dict(ProblemColumn.GROUP_CHOICES).get(getattr(column, 'group_role', ''), 'configured')
            raise serializers.ValidationError(f'User must belong to the {group_label} group.')
        return profile.user.email or profile.user.username
    if kind == ProblemColumn.TYPE_BRAND:
        if not isinstance(value, str) or not value.strip():
            raise serializers.ValidationError('Select a brand.')
        from customers.models import Customer
        from customers.normalization import normalize_brand
        needle = normalize_brand(value)
        canonical = next((
            (candidate.brand or '').strip()
            for candidate in Customer.objects.exclude(brand='').only('brand')
            if normalize_brand(candidate.brand) == needle
        ), '')
        if not canonical:
            raise serializers.ValidationError('Select a brand from the current Customer Export.')
        return canonical
    if kind == ProblemColumn.TYPE_DISTRIBUTOR:
        if not isinstance(value, str) or not value.strip():
            raise serializers.ValidationError('Select a distributor company.')
        from customers.models import Customer
        from customers.normalization import customer_type_is
        customer = next((
            candidate for candidate in Customer.objects.filter(company_name__iexact=value.strip())
            if customer_type_is(candidate.customer_type, 'Distributor')
        ), None)
        if not customer:
            raise serializers.ValidationError('Select a company whose CoyType is Distributor.')
        return customer.company_name
    if kind == ProblemColumn.TYPE_END_USER:
        if not isinstance(value, str) or not value.strip():
            raise serializers.ValidationError('Select an end user company.')
        from customers.models import Customer
        from customers.normalization import customer_type_is
        customer = next((
            candidate for candidate in Customer.objects.filter(company_name__iexact=value.strip())
            if customer_type_is(candidate.customer_type, 'End User')
        ), None)
        if not customer:
            raise serializers.ValidationError('Select a company whose CoyType is End User.')
        return customer.company_name
    if kind == ProblemColumn.TYPE_CLIENT_EMAIL:
        # Client Email is a row-local list. Imported customer records provide
        # suggestions, but users can deliberately add an address that is not in
        # the latest Customer Export. Accept the old single-string format for
        # backwards compatibility and normalize it to a list.
        raw_values = value if isinstance(value, list) else [value]
        cleaned = []
        seen = set()
        for raw_email in raw_values:
            if not isinstance(raw_email, str) or not raw_email.strip():
                raise serializers.ValidationError('Client Email values must be email addresses.')
            email = raw_email.strip().lower()
            try:
                validate_email(email)
            except DjangoValidationError:
                raise serializers.ValidationError(f'Invalid client email address: {raw_email}.')
            if email in seen:
                continue
            seen.add(email)
            cleaned.append(email)
        return cleaned
    if kind == ProblemColumn.TYPE_NUMBER:
        if isinstance(value, bool):
            raise serializers.ValidationError('Must be a number.')
        try:
            return float(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError('Must be a number.')
    if kind == ProblemColumn.TYPE_CHOICE:
        if value not in column.choices:
            raise serializers.ValidationError(f'Must be one of: {", ".join(column.choices)}')
        return value
    if kind == ProblemColumn.TYPE_MULTI_CHOICE:
        if not isinstance(value, list):
            raise serializers.ValidationError('Must be a list of choices.')
        invalid = [x for x in value if x not in column.choices]
        if invalid:
            raise serializers.ValidationError(f'Invalid choice(s): {", ".join(map(str, invalid))}')
        return value
    if kind == ProblemColumn.TYPE_DATE:
        if not isinstance(value, str) or parse_date(value) is None:
            raise serializers.ValidationError('Must be a valid date (YYYY-MM-DD).')
        return value
    if kind == ProblemColumn.TYPE_DATETIME:
        if not isinstance(value, str) or parse_datetime(value) is None:
            raise serializers.ValidationError('Must be a valid date and time.')
        return value
    if kind == ProblemColumn.TYPE_TIME:
        if not isinstance(value, str) or parse_time(value) is None:
            raise serializers.ValidationError('Must be a valid time.')
        return value
    if kind == ProblemColumn.TYPE_BOOLEAN:
        if not isinstance(value, bool):
            raise serializers.ValidationError('Must be true or false.')
        return value
    if kind == ProblemColumn.TYPE_EMAIL:
        try:
            validate_email(value)
        except DjangoValidationError:
            raise serializers.ValidationError('Must be a valid email address.')
        return value
    if kind == ProblemColumn.TYPE_URL:
        try:
            URLValidator()(value)
        except DjangoValidationError:
            raise serializers.ValidationError('Must be a valid URL.')
        return value
    return value


class ShippingProblemSampleSerializer(serializers.ModelSerializer):
    table_name = serializers.CharField(source='table.name', read_only=True)
    container_id = serializers.CharField(source='container.container_id', read_only=True)
    workflow_status = serializers.SerializerMethodField()
    pt_days = serializers.IntegerField(source='table.pt_days', read_only=True)
    days_until_automatic_disposal = serializers.SerializerMethodField()
    tracking_url = serializers.SerializerMethodField()
    tracking_link_expiry = serializers.SerializerMethodField()
    container_disposed = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSample
        fields = [
            'id', 'problem_number', 'table', 'table_name', 'container_id', 'workflow_status',
            'brand', 'distributor', 'end_user', 'als_tracking_number', 'courier',
            'courier_tracking_number', 'custom_values', 'pt_days', 'customer_notified_at',
            'days_until_automatic_disposal', 'tracking_url', 'tracking_link_expiry', 'container_disposed', 'created_at', 'modified_at',
        ]
        read_only_fields = fields

    def get_workflow_status(self, obj):
        return obj.workflow_status

    def get_container_disposed(self, obj):
        return bool(obj.container_id and obj.container and obj.container.disposed_at)

    def get_days_until_automatic_disposal(self, obj):
        return obj.days_until_automatic_disposal

    def get_tracking_url(self, obj):
        if not obj.acknowledgement_token:
            return ''
        base = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        return f'{base}/track/{obj.acknowledgement_token}' if base else f'/track/{obj.acknowledgement_token}'

    def get_tracking_link_expiry(self, obj):
        return obj.tracking_link_expires_at


class ProblemSampleSerializer(serializers.ModelSerializer):
    comments = CommentSerializer(many=True, read_only=True)
    images = ImageSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    history = HistorySerializer(many=True, read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    modified_by_email = serializers.EmailField(source='modified_by.email', read_only=True)
    table_name = serializers.CharField(source='table.name', read_only=True)
    search_score = serializers.FloatField(read_only=True, required=False)
    container_id = serializers.CharField(source='container.container_id', read_only=True)
    container_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    pt_days = serializers.IntegerField(source='table.pt_days', read_only=True)
    expires_at = serializers.SerializerMethodField()
    expiration_status = serializers.SerializerMethodField()
    days_until_expiration = serializers.SerializerMethodField()
    days_until_automatic_disposal = serializers.SerializerMethodField()
    acknowledgement_url = serializers.SerializerMethodField()
    tracking_url = serializers.SerializerMethodField()
    tracking_link_expiry = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSample
        fields = '__all__'
        read_only_fields = ['problem_number', 'container', 'customer_notified_at', 'automatic_disposal_started_at', 'acknowledgement_token', 'acknowledged_at', 'acknowledgement_status_changed_at', 'customer_acknowledgement_action', 'created_by', 'modified_by', 'created_at', 'modified_at']

    def get_expires_at(self, obj):
        return obj.expires_at

    def get_expiration_status(self, obj):
        return obj.expiration_status

    def get_acknowledgement_url(self, obj):
        if not obj.acknowledgement_token:
            return ''
        base = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        return f'{base}/track/{obj.acknowledgement_token}' if base else f'/track/{obj.acknowledgement_token}'

    def get_tracking_url(self, obj):
        return self.get_acknowledgement_url(obj)

    def get_tracking_link_expiry(self, obj):
        return obj.tracking_link_expires_at

    def get_days_until_expiration(self, obj):
        expires_at = obj.expires_at
        if expires_at is None:
            return None
        return max(0, math.ceil((expires_at - timezone.now()).total_seconds() / 86400))

    def get_days_until_automatic_disposal(self, obj):
        return obj.days_until_automatic_disposal

    def validate(self, attrs):
        instance = self.instance
        container_code = attrs.pop('container_code', None)
        if instance is None:
            container = ProblemContainer.resolve_identifier(container_code)
            if not container:
                raise serializers.ValidationError({
                    'container_code': 'Enter a valid Container ID or create a new container before saving the problem sample.'
                })
            if container.disposed_at:
                raise serializers.ValidationError({'container_code': 'A problem sample cannot be assigned to a disposed container. Undo that container disposal first.'})
            attrs['container'] = container
        elif container_code:
            container = ProblemContainer.resolve_identifier(container_code)
            if not container:
                raise serializers.ValidationError({'container_code': 'Container not found.'})
            if instance.container_id and instance.container_id != container.pk:
                if instance.container and instance.container.disposed_at:
                    raise serializers.ValidationError({'container_code': 'A problem sample cannot be moved out of a disposed container. Undo that container disposal first.'})
                if container.disposed_at:
                    raise serializers.ValidationError({'container_code': 'A problem sample cannot be moved into a disposed container. Undo that container disposal first.'})
                attrs['container'] = container
            elif not instance.container_id:
                if container.disposed_at:
                    raise serializers.ValidationError({'container_code': 'A problem sample cannot be assigned to a disposed container. Undo that container disposal first.'})
                attrs['container'] = container
        table = attrs.get('table') or (instance.table if instance else None)
        if instance and 'table' in attrs and attrs['table'] != instance.table:
            raise serializers.ValidationError({'table': 'Move between tables is not supported. Create a new row in the target table instead.'})
        if not table:
            table = ProblemTable.objects.filter(is_default=True).first() or ProblemTable.objects.first()
            if table:
                attrs['table'] = table

        if not table:
            raise serializers.ValidationError({'table': 'A problem sample table is required.'})

        incoming = attrs.get('custom_values', None)
        if incoming is None:
            merged = dict(instance.custom_values if instance else {})
        else:
            if not isinstance(incoming, dict):
                raise serializers.ValidationError({'custom_values': 'Must be an object keyed by column key.'})
            merged = dict(instance.custom_values if instance else {})
            merged.update(incoming)

        columns = {
            c.field_key: c for c in table.columns.all()
            if not c.is_system or c.field_key == 'status'
        }
        # Problem ID is always server-generated. Status is the one built-in row field users can change.
        merged.pop('problem-id', None)
        if _is_empty(merged.get('status')):
            merged['status'] = PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL

        # Fixed Value columns are controlled by the column definition, never by
        # an individual row. Re-apply them on both create and update so clients
        # cannot override a table-wide fixed value.
        for key, column in columns.items():
            if column.column_type == ProblemColumn.TYPE_FIXED:
                merged[key] = copy.deepcopy(column.default_value)

        # Row Creator is server-controlled. On creation it is the authenticated
        # user's company email (or username fallback). On updates the original
        # creator is preserved even if a client submits a different value.
        request = self.context.get('request')
        request_user = getattr(request, 'user', None)
        for key, column in columns.items():
            if column.column_type != ProblemColumn.TYPE_ROW_CREATOR:
                continue
            if instance is None:
                creator = ''
                if request_user is not None and getattr(request_user, 'is_authenticated', False):
                    creator = (getattr(request_user, 'email', '') or getattr(request_user, 'username', '') or '').strip()
                merged[key] = creator
            else:
                old_values = instance.custom_values or {}
                creator = old_values.get(key)
                if _is_empty(creator):
                    original_user = getattr(instance, 'created_by', None)
                    creator = (getattr(original_user, 'email', '') or getattr(original_user, 'username', '') or instance.legacy_created_by or '').strip()
                merged[key] = creator

        # Recent Row Modifier is also server-controlled. It always reflects the
        # authenticated user performing the current create/save operation. A client
        # cannot forge or preserve another value for this column.
        for key, column in columns.items():
            if column.column_type != ProblemColumn.TYPE_RECENT_ROW_MODIFIER:
                continue
            modifier = ''
            if request_user is not None and getattr(request_user, 'is_authenticated', False):
                modifier = (getattr(request_user, 'email', '') or getattr(request_user, 'username', '') or '').strip()
            if not modifier and instance is not None:
                modifier_user = getattr(instance, 'modified_by', None)
                modifier = (
                    getattr(modifier_user, 'email', '')
                    or getattr(modifier_user, 'username', '')
                    or instance.legacy_modified_by
                    or ''
                ).strip()
            merged[key] = modifier

        # Apply ordinary column defaults on row creation. The frontend also
        # prefills these values, but enforcing them here keeps API-created rows
        # consistent too.
        if instance is None:
            for key, column in columns.items():
                if column.column_type not in {ProblemColumn.TYPE_FIXED, ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER} and _is_empty(merged.get(key)) and not _is_empty(column.default_value):
                    merged[key] = copy.deepcopy(column.default_value)

        errors = {}
        for key in list(merged):
            if key not in columns:
                errors[key] = 'This column does not exist in the selected table.'
                continue
            try:
                column = columns[key]
                old_values = (instance.custom_values or {}) if instance else {}
                old_value = old_values.get(key) if instance else None
                keep_historical = False
                if instance is not None and merged[key] == old_value:
                    if column.column_type in {ProblemColumn.TYPE_GROUP, ProblemColumn.TYPE_DISTRIBUTOR, ProblemColumn.TYPE_END_USER, ProblemColumn.TYPE_BRAND}:
                        # Keep historical assignments stable when external directory data changes.
                        keep_historical = True
                    elif column.column_type == ProblemColumn.TYPE_CLIENT_EMAIL:
                        dependencies = _client_email_dependency_columns(column)
                        dependency_unchanged = all(
                            merged.get(dependency.field_key) == old_values.get(dependency.field_key)
                            for dependency in dependencies
                        )
                        keep_historical = dependency_unchanged
                if not keep_historical:
                    # Client Email validation needs access to the dependency value from this row.
                    column._row_values = merged
                    try:
                        merged[key] = _validate_custom_value(column, merged[key])
                    finally:
                        if hasattr(column, '_row_values'):
                            delattr(column, '_row_values')
            except serializers.ValidationError as exc:
                errors[key] = exc.detail

        status_value = str(merged.get('status') or '').strip()
        allowed_statuses = table.status_choices()
        if status_value not in allowed_statuses:
            errors['status'] = 'Choose a valid status for this table.'


        for key, column in columns.items():
            if column.required and _is_empty(merged.get(key)):
                errors[key] = 'This field is required.'

        if errors:
            raise serializers.ValidationError({'custom_values': errors})

        attrs['custom_values'] = merged
        attrs['status'] = status_value
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        values = dict(data.get('custom_values') or {})
        values['problem-id'] = instance.problem_number
        values['status'] = str(values.get('status') or instance.status or PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL)
        if instance.table_id:
            for column in instance.table.columns.all():
                if column.column_type == ProblemColumn.TYPE_FIXED:
                    values[column.field_key] = copy.deepcopy(column.default_value)
                elif column.column_type == ProblemColumn.TYPE_ROW_CREATOR and _is_empty(values.get(column.field_key)):
                    original_user = getattr(instance, 'created_by', None)
                    values[column.field_key] = (getattr(original_user, 'email', '') or getattr(original_user, 'username', '') or instance.legacy_created_by or '').strip()
                elif column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER and _is_empty(values.get(column.field_key)):
                    modifier_user = getattr(instance, 'modified_by', None)
                    values[column.field_key] = (
                        getattr(modifier_user, 'email', '')
                        or getattr(modifier_user, 'username', '')
                        or instance.legacy_modified_by
                        or getattr(getattr(instance, 'created_by', None), 'email', '')
                        or getattr(getattr(instance, 'created_by', None), 'username', '')
                        or instance.legacy_created_by
                        or ''
                    ).strip()
        data['custom_values'] = values
        return data
