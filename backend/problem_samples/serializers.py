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
from .models import ProblemSample, ProblemComment, ProblemMention, ProblemImage, ProblemAttachment, ProblemTable, ProblemColumn, ProblemHistory, ProblemContainer, CURRENT_WORKFLOW_DEFAULT, TERMINAL_PROBLEM_STATUSES, ROUTED_PROBLEM_STATUSES, CURRENT_WORKFLOW_CHOICES, PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_BACK_TO_TESTING, SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY, DISPOSE_AUTOMATICALLY_NO, DISPOSE_AUTOMATICALLY_CHOICES, SYSTEM_TRACKING_LINK_FIELD_KEY, SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY, apply_intercolumn_rules_to_values, resolve_problem_type, FORM_MASK_STATES, INTERCOLUMN_RULE_DIRECTIONS, INTERCOLUMN_RULE_OTHER_TO_CONTROLLER, INTERCOLUMN_RULE_CONTROLLER_TO_OTHER, INTERCOLUMN_RULE_BOTH

MENTION_EMAIL_SUFFIX = '@alsglobal.com'

def _mention_handle(username):
    username = str(username or '').strip()
    if username.lower().endswith(MENTION_EMAIL_SUFFIX):
        return username[:-len(MENTION_EMAIL_SUFFIX)]
    return username



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
            'client_email_dependencies', 'client_email_dependency_details', 'intercolumn_rules', 'form_mask_rules', 'distributor_cc_rules', 'position', 'is_system',
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
                    .select_related('user').order_by('user__first_name', 'user__last_name', 'user__username'))
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
            raise serializers.ValidationError({'name': 'Ticket ID is reserved as a built-in column.'})
        if reserved in {'current-workflow'}:
            raise serializers.ValidationError({'name': 'Current Workflow is reserved as a built-in column.'})
        if reserved in {'dispose-automatically'}:
            raise serializers.ValidationError({'name': 'Dispose Automatically is reserved as a built-in column.'})
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
        if self.instance and column_type != self.instance.column_type:
            referenced_by = []
            for controller in self.instance.table.columns.filter(column_type=ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER).exclude(pk=self.instance.pk):
                if any(str(rule.get('other_column_id') or '') == str(self.instance.pk) for rule in (controller.intercolumn_rules or [])):
                    referenced_by.append(controller.name)
            if referenced_by:
                raise serializers.ValidationError({
                    'column_type': f'Remove the Intercolumn Value Controller rule(s) in {", ".join(referenced_by)} before changing this field type.'
                })
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

        rules = attrs.get(
            'intercolumn_rules',
            getattr(self.instance, 'intercolumn_rules', []) if self.instance else [],
        ) or []
        if column_type == ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER:
            if not isinstance(rules, list):
                raise serializers.ValidationError({'intercolumn_rules': 'Rules must be a list.'})
            if not table:
                raise serializers.ValidationError({'intercolumn_rules': 'Choose a table before configuring rules.'})
            eligible_types = {
                ProblemColumn.TYPE_TEXT, ProblemColumn.TYPE_LONG_TEXT, ProblemColumn.TYPE_NUMBER,
                ProblemColumn.TYPE_CHOICE, ProblemColumn.TYPE_DATE, ProblemColumn.TYPE_DATE_TODAY, ProblemColumn.TYPE_DATETIME,
                ProblemColumn.TYPE_TIME, ProblemColumn.TYPE_BOOLEAN, ProblemColumn.TYPE_EMAIL,
                ProblemColumn.TYPE_PHONE, ProblemColumn.TYPE_URL, ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER,
            }
            editable_system_keys = {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY}
            cleaned_rules = []
            for index, raw_rule in enumerate(rules, start=1):
                if not isinstance(raw_rule, dict):
                    raise serializers.ValidationError({'intercolumn_rules': f'Rule {index} must be an object.'})
                other_id = str(raw_rule.get('other_column_id') or '').strip()
                try:
                    other = table.columns.filter(pk=other_id).first() if other_id else None
                except (DjangoValidationError, ValueError):
                    other = None
                if not other:
                    raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: choose another field.'})
                if self.instance and other.pk == self.instance.pk:
                    raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: a controller cannot reference itself as the other field.'})
                if other.is_system and other.field_key not in editable_system_keys:
                    raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: {other.name} is read-only and cannot be controlled.'})
                if not other.is_system and other.column_type not in eligible_types:
                    raise serializers.ValidationError({
                        'intercolumn_rules': f'Rule {index}: {other.name} is not a supported single-value field for intercolumn rules.'
                    })
                direction = str(raw_rule.get('direction') or '').strip()
                if direction not in INTERCOLUMN_RULE_DIRECTIONS:
                    raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: choose a valid direction.'})

                cleaned = {'other_column_id': other_id, 'direction': direction}
                if direction in {INTERCOLUMN_RULE_OTHER_TO_CONTROLLER, INTERCOLUMN_RULE_BOTH}:
                    trigger = raw_rule.get('when_other_equals')
                    result = raw_rule.get('set_controller_to')
                    if _is_empty(trigger):
                        raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: enter the other-field trigger value.'})
                    if _is_empty(result):
                        raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: enter the controller value to assign.'})
                    try:
                        cleaned['when_other_equals'] = _validate_custom_value(other, trigger)
                    except serializers.ValidationError as exc:
                        raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: invalid trigger for {other.name}: {exc.detail}'})
                    if not isinstance(result, str):
                        result = str(result)
                    cleaned['set_controller_to'] = result
                else:
                    cleaned['when_other_equals'] = None
                    cleaned['set_controller_to'] = None

                if direction in {INTERCOLUMN_RULE_CONTROLLER_TO_OTHER, INTERCOLUMN_RULE_BOTH}:
                    trigger = raw_rule.get('when_controller_equals')
                    result = raw_rule.get('set_other_to')
                    if _is_empty(trigger):
                        raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: enter the controller trigger value.'})
                    if _is_empty(result):
                        raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: enter the value to assign to {other.name}.'})
                    if not isinstance(trigger, str):
                        trigger = str(trigger)
                    cleaned['when_controller_equals'] = trigger
                    try:
                        cleaned['set_other_to'] = _validate_custom_value(other, result)
                    except serializers.ValidationError as exc:
                        raise serializers.ValidationError({'intercolumn_rules': f'Rule {index}: invalid assigned value for {other.name}: {exc.detail}'})
                else:
                    cleaned['when_controller_equals'] = None
                    cleaned['set_other_to'] = None
                cleaned_rules.append(cleaned)
            attrs['intercolumn_rules'] = cleaned_rules
        else:
            attrs['intercolumn_rules'] = []

        if column_type == ProblemColumn.TYPE_GROUP:
            if group_role not in {ProblemColumn.GROUP_LAB_TECHNICIAN, ProblemColumn.GROUP_CUSTOMER_SERVICE}:
                raise serializers.ValidationError({'group_role': 'Choose either Lab or Customer Service.'})
            attrs['group_role'] = group_role
        else:
            attrs['group_role'] = ''

        choices = attrs.get('choices', getattr(self.instance, 'choices', [])) or []
        if column_type in {ProblemColumn.TYPE_CHOICE, ProblemColumn.TYPE_MULTI_CHOICE, ProblemColumn.TYPE_PROBLEM_TYPE}:
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

        # Automatic customer-notification CC rules belong only to Distributor fields.
        # Validate on the server so admins cannot persist invalid addresses/patterns.
        if column_type == ProblemColumn.TYPE_DISTRIBUTOR:
            rules = attrs.get('distributor_cc_rules', getattr(self.instance, 'distributor_cc_rules', [])) or []
            if not isinstance(rules, list) or len(rules) > 30:
                raise serializers.ValidationError({'distributor_cc_rules': 'Provide up to 30 matching rules.'})
            cleaned_rules = []
            modes = {'exact', 'contains', 'starts_with', 'ends_with', 'wildcard'}
            for index, rule in enumerate(rules, start=1):
                if not isinstance(rule, dict):
                    raise serializers.ValidationError({'distributor_cc_rules': f'Rule {index} must be an object.'})
                mode = rule.get('match_type')
                pattern = rule.get('pattern')
                addresses = rule.get('cc_emails')
                if mode not in modes:
                    raise serializers.ValidationError({'distributor_cc_rules': f'Rule {index}: select a matching method.'})
                if not isinstance(pattern, str) or not pattern.strip() or len(pattern.strip()) > 160:
                    raise serializers.ValidationError({'distributor_cc_rules': f'Rule {index}: pattern must be 1 to 160 characters.'})
                if not isinstance(addresses, list) or not 1 <= len(addresses) <= 20:
                    raise serializers.ValidationError({'distributor_cc_rules': f'Rule {index}: enter 1 to 20 CC addresses.'})
                cleaned = []
                seen = set()
                for address in addresses:
                    if not isinstance(address, str):
                        raise serializers.ValidationError({'distributor_cc_rules': f'Rule {index}: invalid CC address.'})
                    address = address.strip()
                    try:
                        validate_email(address)
                    except DjangoValidationError:
                        raise serializers.ValidationError({'distributor_cc_rules': f'Rule {index}: invalid CC address: {address}.'})
                    if address.casefold() not in seen:
                        cleaned.append(address)
                        seen.add(address.casefold())
                cleaned_rules.append({'match_type': mode, 'pattern': pattern.strip(), 'cc_emails': cleaned})
            attrs['distributor_cc_rules'] = cleaned_rules
        else:
            attrs['distributor_cc_rules'] = []

        # A mask is a choice field whose selections define explicit creation-time
        # visibility. Column keys are stable UUIDs, not mutable field names.
        if column_type == ProblemColumn.TYPE_PROBLEM_TYPE:
            raw_masks = attrs.get('form_mask_rules', getattr(self.instance, 'form_mask_rules', {})) or {}
            if not isinstance(raw_masks, dict):
                raise serializers.ValidationError({'form_mask_rules': 'Mask rules must be an object keyed by choice.'})
            unknown = set(raw_masks) - set(attrs['choices'])
            if unknown:
                raise serializers.ValidationError({'form_mask_rules': f'Rules reference unknown choices: {", ".join(sorted(unknown))}.'})
            all_columns = {str(candidate.pk): candidate for candidate in table.columns.all()} if table else {}
            cleaned_masks = {}
            for choice in attrs['choices']:
                config = raw_masks.get(choice, {})
                if not isinstance(config, dict):
                    raise serializers.ValidationError({'form_mask_rules': f'{choice}: expected a rule object.'})
                raw_columns = config.get('columns', {})
                if not isinstance(raw_columns, dict):
                    raise serializers.ValidationError({'form_mask_rules': f'{choice}: columns must be an object.'})
                cleaned_columns = {}
                for col_id, state in raw_columns.items():
                    target = all_columns.get(str(col_id))
                    if target is None or (self.instance and target.pk == self.instance.pk):
                        raise serializers.ValidationError({'form_mask_rules': f'{choice}: one referenced column is missing or is this mask.'})
                    if target.column_type == ProblemColumn.TYPE_PROBLEM_TYPE:
                        raise serializers.ValidationError({'form_mask_rules': f'{choice}: mask columns must always remain visible.'})
                    if state not in FORM_MASK_STATES:
                        raise serializers.ValidationError({'form_mask_rules': f'{choice}: invalid state for {target.name}.'})
                    if (target.required and state != 'required'
                            and target.column_type not in {ProblemColumn.TYPE_FIXED, ProblemColumn.TYPE_ROW_CREATOR,
                                                           ProblemColumn.TYPE_RECENT_ROW_MODIFIER, ProblemColumn.TYPE_DATE_TODAY}
                            and target.field_key not in {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY}
                            and (target.default_value is None or target.default_value == '' or target.default_value == [])):
                        raise serializers.ValidationError({'form_mask_rules': f'{choice}: {target.name} is database-required. Give it a default before marking it {state}.'})
                    cleaned_columns[str(col_id)] = state
                images = config.get('images')
                attachments = config.get('attachments')
                if (images is not None and images not in FORM_MASK_STATES) or (attachments is not None and attachments not in FORM_MASK_STATES):
                    raise serializers.ValidationError({'form_mask_rules': f'{choice}: invalid image or attachment state.'})
                customer_details = config.get('customer_details', '')
                if not isinstance(customer_details, str):
                    raise serializers.ValidationError({'form_mask_rules': f'{choice}: customer details must be text.'})
                if len(customer_details.strip()) > 8000:
                    raise serializers.ValidationError({'form_mask_rules': f'{choice}: customer details must be 8000 characters or fewer.'})
                cleaned_masks[choice] = {'columns': cleaned_columns, **({'images': images} if images is not None else {}), **({'attachments': attachments} if attachments is not None else {}), **({'customer_details': customer_details.strip()} if customer_details.strip() else {})}
            attrs['form_mask_rules'] = cleaned_masks
        else:
            attrs['form_mask_rules'] = {}

        # Fixed Value, Row Creator, and Recent Row Modifier columns are read-only
        # on individual rows. The two user-audit types are populated by the server.
        # Historical imported rows may not have user metadata, so they are not required.
        if column_type == ProblemColumn.TYPE_FIXED:
            attrs['required'] = True
        elif column_type in {ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER}:
            attrs['required'] = False
            attrs['default_value'] = None
        elif column_type == ProblemColumn.TYPE_DATE_TODAY:
            # Date (Today) has a dynamic default evaluated per ticket, so never
            # persist a static date in the column definition.
            attrs['default_value'] = None

        # Keep the column default compatible with its configured type. The same
        # validator is used for row values so defaults cannot introduce data that
        # the row serializer would later reject.
        default_value = attrs.get('default_value', getattr(self.instance, 'default_value', None))
        if column_type in {ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER, ProblemColumn.TYPE_DATE_TODAY}:
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
                and column_type not in {ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER, ProblemColumn.TYPE_DATE_TODAY}):
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
        # Do not let a later edit of a database-required column invalidate
        # existing masks by removing the default those masks depend on.
        if (self.instance is not None and table and required
                and column_type not in {ProblemColumn.TYPE_FIXED, ProblemColumn.TYPE_ROW_CREATOR,
                                        ProblemColumn.TYPE_RECENT_ROW_MODIFIER, ProblemColumn.TYPE_DATE_TODAY}
                and self.instance.field_key not in {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY}
                and attrs.get('default_value') is None):
            for mask in table.columns.filter(column_type=ProblemColumn.TYPE_PROBLEM_TYPE).exclude(pk=self.instance.pk):
                for choice, configuration in (mask.form_mask_rules or {}).items():
                    state = (configuration.get('columns') or {}).get(str(self.instance.pk)) if isinstance(configuration, dict) else None
                    if state in {'hidden', 'shown'}:
                        raise serializers.ValidationError({
                            'default_value': f'{mask.name} ({choice}) makes this required field optional or hidden. Configure a default value first.'
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
    author_username = serializers.CharField(source='author.username', read_only=True)
    author_name = serializers.SerializerMethodField()
    mentions = serializers.SerializerMethodField()

    class Meta:
        model = ProblemComment
        fields = ['id', 'body', 'author_email', 'author_username', 'author_name', 'legacy_author', 'mentions', 'created_at']

    def get_author_name(self, obj):
        if not obj.author:
            return ''
        return obj.author.get_full_name().strip() or obj.author.username

    def get_mentions(self, obj):
        return [
            {
                'id': mention.mentioned_user_id,
                'username': _mention_handle(mention.mentioned_user.username),
                'name': mention.mentioned_user.get_full_name().strip() or _mention_handle(mention.mentioned_user.username),
            }
            for mention in obj.mentions.all()
        ]


class ImageSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)
    size_bytes = serializers.SerializerMethodField()
    has_image = serializers.SerializerMethodField()

    class Meta:
        model = ProblemImage
        # Deliberately do not expose the ImageField URL here. Behind a reverse
        # proxy Django/DRF can turn it into an absolute storage URL (and, if
        # proxy scheme information is not trusted, even an http:// URL). Staff
        # previews are authenticated and must always stream through the
        # image-content API instead of /media/.
        fields = ['id', 'original_name', 'size_bytes', 'has_image', 'include_in_customer_notification', 'uploaded_by_email', 'uploaded_at']

    def get_size_bytes(self, obj):
        try:
            return obj.image.size if obj.image else 0
        except (OSError, ValueError):
            return 0

    def get_has_image(self, obj):
        return bool(obj.image)


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)

    class Meta:
        model = ProblemAttachment
        fields = ['id', 'file', 'original_name', 'content_type', 'size_bytes', 'include_in_customer_notification', 'uploaded_by_email', 'uploaded_at']


class HistorySerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)
    actor_name = serializers.SerializerMethodField()
    action_label = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = ProblemHistory
        fields = ['id', 'action', 'action_label', 'summary', 'details', 'actor_email', 'actor_name', 'created_at']

    def get_summary(self, obj):
        if obj.action == ProblemHistory.ACTION_CREATED:
            return 'Created ticket'
        if obj.action == ProblemHistory.ACTION_CUSTOMER_NOTIFICATION:
            # Preserve the event-specific wording stored when the email was
            # confirmed. In particular, the first notification records that
            # the tracking link was sent to the customer.
            return (obj.summary or 'Sent an email to the customer').replace('problem sample', 'ticket').replace('Problem Sample', 'Ticket')
        if obj.action == ProblemHistory.ACTION_ACKNOWLEDGED:
            return 'Customer acknowledged ticket'
        return obj.summary

    def get_action_label(self, obj):
        if obj.action == ProblemHistory.ACTION_ACKNOWLEDGED:
            return 'Customer acknowledged ticket'
        return obj.get_action_display()

    def get_actor_name(self, obj):
        if not obj.actor:
            details = obj.details or {}
            if details.get('automatic'):
                return 'System'
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
    source_container_id = serializers.SerializerMethodField()
    restored_to_container_id = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    samples = serializers.SerializerMethodField()

    class Meta:
        model = ProblemContainer
        fields = [
            'id', 'container_id', 'sample_count', 'expired_count', 'active_count',
            'unnotified_count', 'all_expired', 'ready_to_dispose', 'status', 'samples',
            'created_by_email', 'created_at', 'disposed_at', 'disposed_by_email',
            'is_dumping', 'source_container_id', 'dumped_sample_ids',
            'restored_at', 'restored_to_container_id',
        ]
        read_only_fields = fields

    def get_source_container_id(self, obj):
        return obj.source_container.container_id if obj.source_container_id else None

    def get_restored_to_container_id(self, obj):
        return obj.restored_to_container.container_id if obj.restored_to_container_id else None

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
        return sample.workflow_status in {PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_DISPOSED}

    def get_ready_to_dispose(self, obj):
        if obj.is_dumping:
            return False
        samples = self._samples(obj)
        return bool(samples) and all(self._sample_ready_for_disposal(sample) for sample in samples)

    def get_status(self, obj):
        if obj.is_dumping and obj.restored_at:
            return 'restored'
        if obj.disposed_at:
            return 'disposed'
        all_samples = self._samples(obj)
        if not all_samples:
            return 'empty'
        samples = all_samples
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
                'created_at': sample.created_at,
                'created_date': timezone.localdate(sample.created_at).isoformat(),
                'expires_at': expires_at,
                'expiration_status': sample.expiration_status,
                'current_workflow': sample.workflow_status,
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
    if kind in {ProblemColumn.TYPE_TEXT, ProblemColumn.TYPE_LONG_TEXT, ProblemColumn.TYPE_FIXED, ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER, ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER}:
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
    if kind in {ProblemColumn.TYPE_DISTRIBUTOR, ProblemColumn.TYPE_END_USER}:
        # Distributor and End User are free-text fields. Their column type only
        # determines which Customer Export suggestion source is shown in the UI;
        # a user is never required to choose one of those suggestions.
        if not isinstance(value, str):
            raise serializers.ValidationError('Must be text.')
        return value
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
    if kind in {ProblemColumn.TYPE_CHOICE, ProblemColumn.TYPE_PROBLEM_TYPE}:
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
    if kind in {ProblemColumn.TYPE_DATE, ProblemColumn.TYPE_DATE_TODAY}:
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
    if kind == ProblemColumn.TYPE_PHONE:
        if not isinstance(value, str):
            raise serializers.ValidationError('Must be a phone number.')
        phone = value.strip()
        if len(phone) > 50:
            raise serializers.ValidationError('Phone number must be 50 characters or fewer.')
        # Preserve staff-entered formatting while accepting common international
        # and extension forms such as +1 (780) 555-1234 ext 42.
        if not re.fullmatch(r'\+?[0-9\s().-]+(?:\s*(?:x|ext\.?|extension)\s*[0-9]{1,10})?', phone, flags=re.IGNORECASE):
            raise serializers.ValidationError('Enter a valid phone number.')
        digits = re.sub(r'\D', '', phone)
        if len(digits) < 7 or len(digits) > 25:
            raise serializers.ValidationError('Enter a phone number with 7 to 25 digits, including any extension.')
        return phone
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
            'days_until_automatic_disposal', 'tracking_url', 'tracking_link_expiry', 'back_to_testing_notified_at', 'container_disposed', 'created_at', 'modified_at',
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
    container_is_dumping = serializers.BooleanField(source='container.is_dumping', read_only=True)
    container_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    create_new_container = serializers.BooleanField(write_only=True, required=False, default=False)
    pt_days = serializers.IntegerField(source='table.pt_days', read_only=True)
    expires_at = serializers.SerializerMethodField()
    expiration_status = serializers.SerializerMethodField()
    days_until_expiration = serializers.SerializerMethodField()
    days_until_automatic_disposal = serializers.SerializerMethodField()
    acknowledgement_token = serializers.SerializerMethodField()
    acknowledgement_url = serializers.SerializerMethodField()
    tracking_url = serializers.SerializerMethodField()
    tracking_link_expiry = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSample
        fields = '__all__'
        read_only_fields = ['problem_number', 'container', 'customer_notified_at', 'automatic_disposal_started_at', 'acknowledgement_token', 'acknowledged_at', 'acknowledgement_status_changed_at', 'customer_acknowledgement_action', 'back_to_testing_notified_at', 'created_by', 'modified_by', 'problem_type_prompts', 'created_at', 'modified_at']

    def get_expires_at(self, obj):
        return obj.expires_at

    def get_expiration_status(self, obj):
        return obj.expiration_status

    def get_acknowledgement_token(self, obj):
        return obj.acknowledgement_token

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
        create_new_container = attrs.pop('create_new_container', False)
        if create_new_container and container_code not in (None, ''):
            raise serializers.ValidationError({
                'container_code': 'Choose either an existing Container ID or create a new container, not both.'
            })
        if create_new_container and instance is None:
            raise serializers.ValidationError({'create_new_container': 'This option is only for reopening existing tickets.'})
        if instance is None:
            if container_code:
                container = ProblemContainer.resolve_identifier(container_code)
                if not container:
                    raise serializers.ValidationError({'container_code': 'Container not found.'})
                if container.disposed_at or container.is_dumping:
                    raise serializers.ValidationError({'container_code': 'A ticket cannot be assigned to a disposed container. Undo that container disposal first.'})
                attrs['container'] = container
        elif container_code and not create_new_container:
            container = ProblemContainer.resolve_identifier(container_code)
            if not container:
                raise serializers.ValidationError({'container_code': 'Container not found.'})
            if instance.container_id and instance.container_id != container.pk:
                if instance.container and instance.container.disposed_at:
                    raise serializers.ValidationError({'container_code': 'A ticket cannot be moved out of a disposed container. Undo that container disposal first.'})
                if container.disposed_at or container.is_dumping:
                    raise serializers.ValidationError({'container_code': 'A ticket cannot be moved into a disposed container. Undo that container disposal first.'})
                attrs['container'] = container
            elif not instance.container_id:
                if container.disposed_at or container.is_dumping:
                    raise serializers.ValidationError({'container_code': 'A ticket cannot be assigned to a disposed container. Undo that container disposal first.'})
                attrs['container'] = container
        elif not create_new_container and instance is not None and container_code == '' and instance.container_id:
            if instance.container and instance.container.disposed_at:
                raise serializers.ValidationError({'container_code': 'Undo container disposal before removing a ticket from it.'})
            attrs['container'] = None
        table = attrs.get('table') or (instance.table if instance else None)
        if instance and 'table' in attrs and attrs['table'] != instance.table:
            raise serializers.ValidationError({'table': 'Move between tables is not supported. Create a new row in the target table instead.'})
        if not table:
            table = ProblemTable.objects.filter(is_default=True).first() or ProblemTable.objects.first()
            if table:
                attrs['table'] = table

        if not table:
            raise serializers.ValidationError({'table': 'A ticket table is required.'})

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
            if not c.is_system or c.field_key in {SYSTEM_CURRENT_WORKFLOW_FIELD_KEY, SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY}
        }
        # Ticket ID is always server-generated. Current Workflow and Dispose
        # Automatically are the built-in routing controls. Ignore the removed
        # legacy Status key from stale clients or historical rows.
        merged.pop('problem-id', None)
        merged.pop('status', None)
        if _is_empty(merged.get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY)):
            merged[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = (instance.workflow_status if instance else CURRENT_WORKFLOW_DEFAULT)
        if _is_empty(merged.get(SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY)):
            merged[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO

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

        # Mask resolution is based on the actual selected mask values. Hidden
        # fields are never accepted from the client during ticket creation.
        mask_decisions = resolve_problem_type(table, merged) if instance is None else {}
        if instance is None:
            for key, decision in mask_decisions.items():
                if decision == 'hidden' and key in columns:
                    merged.pop(key, None)

        # Apply ordinary column defaults on row creation. The frontend also
        # prefills these values, but enforcing them here keeps API-created rows
        # consistent too.
        if instance is None:
            today_value = timezone.localdate().isoformat()
            for key, column in columns.items():
                if column.column_type == ProblemColumn.TYPE_DATE_TODAY and _is_empty(merged.get(key)):
                    merged[key] = today_value
                elif column.column_type not in {ProblemColumn.TYPE_FIXED, ProblemColumn.TYPE_ROW_CREATOR, ProblemColumn.TYPE_RECENT_ROW_MODIFIER} and _is_empty(merged.get(key)) and not _is_empty(column.default_value):
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
                    if column.column_type in {ProblemColumn.TYPE_GROUP, ProblemColumn.TYPE_BRAND}:
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

        if not errors:
            try:
                merged, _ = apply_intercolumn_rules_to_values(table, merged)
            except DjangoValidationError as exc:
                errors['intercolumn_rules'] = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)

        workflow_value = str(merged.get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY) or '').strip()
        if workflow_value not in CURRENT_WORKFLOW_CHOICES:
            errors[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = 'Choose a valid Current Workflow.'

        # Only COMPLETED terminal workflows require an explicit physical
        # container when reopened. Pending "To be..." workflows are not terminal.
        # Never silently reuse the prior container (which may have been reused).
        reactivating = bool(
            instance and instance.workflow_status in TERMINAL_PROBLEM_STATUSES
            and workflow_value not in TERMINAL_PROBLEM_STATUSES
        )
        if create_new_container and not reactivating:
            errors['create_new_container'] = 'A new container can only be created when reopening a terminal ticket.'
        if reactivating:
            if instance.container_id and instance.container and (instance.container.is_dumping or instance.container.disposed_at):
                errors['container_code'] = 'Undo the dumping container disposal before reopening this ticket.'
            elif not create_new_container and not str(container_code or '').strip():
                errors['container_code'] = (
                    'Choose an existing Container ID or create a new container '
                    'before changing a terminal workflow to a non-terminal workflow.'
                )
            if create_new_container and not errors:
                # Delayed until update(): all field validation must pass before
                # a new container is created, and the view wraps save in atomic().
                attrs['create_new_container'] = True
        # The API must enforce this role restriction even if a client sends a
        # crafted PATCH/PUT, or completes a previously prepared ticket. Existing
        # Back to testing tickets can still be edited without changing workflow.
        actor_profile = getattr(request_user, 'tracker_profile', None) if request_user is not None else None
        if (
            actor_profile is not None
            and actor_profile.role == UserProfile.ROLE_CUSTOMER_SERVICE
            and workflow_value == PROBLEM_STATUS_BACK_TO_TESTING
            and (instance is None or instance.workflow_status != PROBLEM_STATUS_BACK_TO_TESTING)
        ):
            errors[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = (
                'Customer Service users cannot change the workflow to Back to testing.'
            )

        # Routed/terminal workflows always stop automatic disposal. This keeps
        # disposal/shipping/testing actions authoritative even if a stale client
        # submits Dispose Automatically = Yes in the same request.
        if workflow_value in ROUTED_PROBLEM_STATUSES:
            merged[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
        if workflow_value in {PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_BACK_TO_TESTING}:
            if instance and instance.container_id and instance.container and instance.container.disposed_at:
                raise serializers.ValidationError({'container_code': 'Undo container disposal before moving this ticket out of it.'})
            attrs['container'] = None

        for key, column in columns.items():
            if column.required and _is_empty(merged.get(key)):
                errors[key] = 'This field is required.'

        if instance is None:
            for key, decision in mask_decisions.items():
                if decision == 'required' and key in columns and _is_empty(merged.get(key)):
                    errors[key] = 'This field is required by the selected Problem Type.'
        if errors:
            raise serializers.ValidationError({'custom_values': errors})

        attrs['custom_values'] = merged
        attrs['current_workflow'] = workflow_value
        return attrs

    def update(self, instance, validated_data):
        create_new_container = validated_data.pop('create_new_container', False)
        if create_new_container:
            actor = getattr(self.context.get('request'), 'user', None)
            validated_data['container'] = ProblemContainer.objects.create(
                created_by=actor if actor and actor.is_authenticated else None,
            )
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        values = dict(data.get('custom_values') or {})
        values['problem-id'] = instance.problem_number
        values.pop('status', None)
        values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = instance.workflow_status
        values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = str(values.get(SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY) or DISPOSE_AUTOMATICALLY_NO)
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
