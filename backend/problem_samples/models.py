import uuid
import json
import secrets
import math
import re
from datetime import timedelta
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models.signals import post_delete
from django.dispatch import receiver


# Status is a descriptive, required built-in field with one fixed set of values
# shared by every problem-sample table. Workflow routing is controlled separately
# by Current Workflow.
PROBLEM_STATUS_NEW = 'NEW'
PROBLEM_STATUS_IN_PROGRESS = 'IN PROGRESS'
PROBLEM_STATUS_ON_HOLD = 'ON HOLD'
PROBLEM_STATUS_SHIPPED_BACK_TO_CLIENT = 'SHIPPED BACK TO CLIENT'
PROBLEM_STATUS_DISPOSED_VALUE = 'DISPOSED'
PROBLEM_STATUS_COMPLETED = 'COMPLETED'
PROBLEM_STATUS_CHOICES = [
    PROBLEM_STATUS_NEW,
    PROBLEM_STATUS_IN_PROGRESS,
    PROBLEM_STATUS_ON_HOLD,
    PROBLEM_STATUS_SHIPPED_BACK_TO_CLIENT,
    PROBLEM_STATUS_DISPOSED_VALUE,
    PROBLEM_STATUS_COMPLETED,
]
PROBLEM_STATUS_DEFAULT = PROBLEM_STATUS_NEW

# Current Workflow is the authoritative system routing field. Its values are
# immutable because disposal, shipping, back-to-testing, tracking-link, and
# CS follow-up queues depend on them.
CURRENT_WORKFLOW_DEFAULT = 'CS Follow-Up'
CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER = 'Waiting For Customer'
PROBLEM_STATUS_TO_BE_DISPOSED = 'To be Disposed'
PROBLEM_STATUS_TO_BE_SHIPPED_BACK = 'To be shipped back to client'
PROBLEM_STATUS_TO_BE_BACK_TO_TESTING = 'To be back to testing'
PROBLEM_STATUS_BACK_TO_TESTING = 'Back to testing'
PROBLEM_STATUS_DISPOSED = 'Disposed'
PROBLEM_STATUS_SHIPPED_BACK = 'Shipped back to client'
TERMINAL_PROBLEM_STATUSES = [
    PROBLEM_STATUS_TO_BE_DISPOSED,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_BACK_TO_TESTING,
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_SHIPPED_BACK,
]
CURRENT_WORKFLOW_CHOICES = [CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER, *TERMINAL_PROBLEM_STATUSES]
# Backward-compatible name used by a few helpers.
SYSTEM_PROBLEM_STATUSES = list(CURRENT_WORKFLOW_CHOICES)

DISPOSE_AUTOMATICALLY_YES = 'Yes'
DISPOSE_AUTOMATICALLY_NO = 'No'
DISPOSE_AUTOMATICALLY_CHOICES = [DISPOSE_AUTOMATICALLY_YES, DISPOSE_AUTOMATICALLY_NO]

CUSTOMER_ACTION_DISPOSE = 'dispose'
CUSTOMER_ACTION_SHIP_BACK = 'ship_back'
CUSTOMER_ACTION_HOLD = 'hold'
CUSTOMER_ACTION_REQUESTED_INFORMATION = 'requested_info'
CUSTOMER_ACTION_CHOICES = [
    (CUSTOMER_ACTION_DISPOSE, 'Dispose Sample(s)'),
    (CUSTOMER_ACTION_SHIP_BACK, 'Ship back samples'),
    (CUSTOMER_ACTION_HOLD, 'Hold sample'),
    (CUSTOMER_ACTION_REQUESTED_INFORMATION, 'Give us more details about this ticket'),
]

TRACKING_LINK_DAYS = 30
TRACKING_LINK_EXPIRING_STATUSES = {
    PROBLEM_STATUS_TO_BE_DISPOSED,
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_SHIPPED_BACK,
    PROBLEM_STATUS_BACK_TO_TESTING,
}
# Legacy aliases kept so historical code/migrations and older clients remain compatible.
ACKNOWLEDGEMENT_LINK_DAYS = TRACKING_LINK_DAYS
ACKNOWLEDGEMENT_EXPIRING_STATUSES = TRACKING_LINK_EXPIRING_STATUSES
ACKNOWLEDGEMENT_PRE_ACK_STATUSES = set()

SYSTEM_CURRENT_WORKFLOW_FIELD_KEY = 'current-workflow'
SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY = 'dispose-automatically'
SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY = 'system-days-until-automatic-disposal'
SYSTEM_TRACKING_LINK_FIELD_KEY = 'system-tracking-link'
SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY = 'system-tracking-link-expiry'


def generate_acknowledgement_token():
    """Return 48 cryptographically random bytes encoded as 64 URL-safe characters."""
    return secrets.token_urlsafe(48)


STRONG_TRACKING_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{64}$')


def is_strong_tracking_token(token):
    return isinstance(token, str) and STRONG_TRACKING_TOKEN_RE.fullmatch(token) is not None


class ProblemTable(models.Model):
    """A user-defined collection of problem samples, similar to a Microsoft List."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_tables_created')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    next_problem_id = models.PositiveBigIntegerField(default=1)
    pt_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(3650)],
        help_text='Automatic-disposal expiration period in days from the most recent change of Dispose Automatically from No to Yes. When the period ends, Current Workflow changes to To be Disposed. Zero means an immediate transition.',
    )
    acknowledgement_link_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(3650)],
        help_text='How many days an acknowledged customer link continues to show the acknowledgement confirmation.',
    )
    def status_choices(self):
        return list(PROBLEM_STATUS_CHOICES)

    def workflow_choices(self):
        return list(CURRENT_WORKFLOW_CHOICES)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ProblemColumn(models.Model):
    TYPE_TEXT = 'text'
    TYPE_LONG_TEXT = 'long_text'
    TYPE_NUMBER = 'number'
    TYPE_CHOICE = 'choice'
    TYPE_MULTI_CHOICE = 'multi_choice'
    TYPE_DATE = 'date'
    TYPE_DATETIME = 'datetime'
    TYPE_TIME = 'time'
    TYPE_BOOLEAN = 'boolean'
    TYPE_EMAIL = 'email'
    TYPE_URL = 'url'
    TYPE_FIXED = 'fixed'
    TYPE_GROUP = 'group'
    TYPE_DISTRIBUTOR = 'distributor'
    TYPE_END_USER = 'end_user'
    TYPE_CLIENT_EMAIL = 'client_email'
    TYPE_ROW_CREATOR = 'row_creator'
    TYPE_RECENT_ROW_MODIFIER = 'recent_row_modifier'
    TYPE_BRAND = 'brand'
    TYPE_INTERCOLUMN_CONTROLLER = 'intercolumn_controller'

    GROUP_LAB_TECHNICIAN = 'lab_technician'
    GROUP_CUSTOMER_SERVICE = 'customer_service'
    GROUP_CHOICES = [
        (GROUP_LAB_TECHNICIAN, 'Lab Technician'),
        (GROUP_CUSTOMER_SERVICE, 'Customer Service'),
    ]

    COLUMN_TYPES = [
        (TYPE_TEXT, 'Single line of text'),
        (TYPE_LONG_TEXT, 'Multiple lines of text'),
        (TYPE_NUMBER, 'Number'),
        (TYPE_CHOICE, 'Choice'),
        (TYPE_MULTI_CHOICE, 'Multiple choice'),
        (TYPE_DATE, 'Date'),
        (TYPE_DATETIME, 'Date and time'),
        (TYPE_TIME, 'Time'),
        (TYPE_BOOLEAN, 'Yes / No'),
        (TYPE_EMAIL, 'Email'),
        (TYPE_URL, 'URL'),
        (TYPE_FIXED, 'Fixed Value'),
        (TYPE_GROUP, 'Group'),
        (TYPE_DISTRIBUTOR, 'Distributor'),
        (TYPE_END_USER, 'End User'),
        (TYPE_BRAND, 'Brand'),
        (TYPE_CLIENT_EMAIL, 'Client Email'),
        (TYPE_ROW_CREATOR, 'Row Creator'),
        (TYPE_RECENT_ROW_MODIFIER, 'Recent Row Modifier'),
        (TYPE_INTERCOLUMN_CONTROLLER, 'Intercolumn Value Controller'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    table = models.ForeignKey(ProblemTable, on_delete=models.CASCADE, related_name='columns')
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    field_key = models.SlugField(max_length=180)
    column_type = models.CharField(max_length=30, choices=COLUMN_TYPES, default=TYPE_TEXT)
    required = models.BooleanField(default=False)
    searchable = models.BooleanField(default=True)
    include_in_customer_notification = models.BooleanField(default=False)
    choices = models.JSONField(default=list, blank=True)
    default_value = models.JSONField(null=True, blank=True)
    group_role = models.CharField(max_length=40, choices=GROUP_CHOICES, blank=True)
    depends_on_column = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='dependent_columns',
        help_text='Legacy first dependency for Client Email columns.',
    )
    client_email_dependencies = models.JSONField(
        default=list, blank=True,
        help_text='Ordered ProblemColumn UUIDs used as Client Email company fallbacks.',
    )
    intercolumn_rules = models.JSONField(
        default=list, blank=True,
        help_text='Directional equality/assignment rules used by Intercolumn Value Controller columns.',
    )
    position = models.PositiveIntegerField(default=0)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['table', 'field_key'], name='unique_problem_column_key_per_table')
        ]

    def ordered_client_email_dependency_columns(self):
        """Return configured Client Email dependency columns in priority order."""
        raw_ids = [str(value) for value in (self.client_email_dependencies or []) if value]
        if not raw_ids and self.depends_on_column_id:
            # Backward compatibility for columns created before prioritized dependencies.
            raw_ids = [str(self.depends_on_column_id)]
        if not raw_ids:
            return []
        by_id = {str(column.id): column for column in self.table.columns.filter(id__in=raw_ids)}
        return [by_id[column_id] for column_id in raw_ids if column_id in by_id]

    def __str__(self):
        return f'{self.table.name}: {self.name}'


INTERCOLUMN_RULE_OTHER_TO_CONTROLLER = 'other_to_controller'
INTERCOLUMN_RULE_CONTROLLER_TO_OTHER = 'controller_to_other'
INTERCOLUMN_RULE_BOTH = 'both'
INTERCOLUMN_RULE_DIRECTIONS = {
    INTERCOLUMN_RULE_OTHER_TO_CONTROLLER,
    INTERCOLUMN_RULE_CONTROLLER_TO_OTHER,
    INTERCOLUMN_RULE_BOTH,
}


def _intercolumn_values_equal(left, right):
    """Exact JSON-style equality with numeric normalization for controller rules."""
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    return left == right


def apply_intercolumn_rules_to_values(table, values):
    """Apply every Intercolumn Value Controller rule to a row-value mapping.

    Rules are stored in canonical validated form on controller columns. They are
    evaluated in column/rule order until a fixed point is reached. Repeated states
    or an excessive number of passes indicate a conflicting rule cycle.
    """
    working = dict(values or {})
    if not table:
        return working, set()
    columns = list(table.columns.all())
    by_id = {str(column.id): column for column in columns}
    controllers = [
        column for column in columns
        if column.column_type == ProblemColumn.TYPE_INTERCOLUMN_CONTROLLER and column.intercolumn_rules
    ]
    if not controllers:
        return working, set()

    changed_keys = set()
    total_rules = sum(len(column.intercolumn_rules or []) for column in controllers)
    max_passes = max(6, total_rules * 4 + 4)
    seen_states = set()

    for _ in range(max_passes):
        state = json.dumps(working, sort_keys=True, default=str, separators=(',', ':'))
        if state in seen_states:
            raise ValidationError('Intercolumn Value Controller rules contain a cycle that does not converge.')
        seen_states.add(state)
        changed = False

        for controller in controllers:
            controller_key = controller.field_key
            for rule in controller.intercolumn_rules or []:
                other = by_id.get(str(rule.get('other_column_id') or ''))
                if other is None:
                    continue
                direction = str(rule.get('direction') or '')

                if direction in {INTERCOLUMN_RULE_OTHER_TO_CONTROLLER, INTERCOLUMN_RULE_BOTH}:
                    if _intercolumn_values_equal(working.get(other.field_key), rule.get('when_other_equals')):
                        assigned = rule.get('set_controller_to')
                        if not _intercolumn_values_equal(working.get(controller_key), assigned):
                            working[controller_key] = assigned
                            changed_keys.add(controller_key)
                            changed = True

                if direction in {INTERCOLUMN_RULE_CONTROLLER_TO_OTHER, INTERCOLUMN_RULE_BOTH}:
                    if _intercolumn_values_equal(working.get(controller_key), rule.get('when_controller_equals')):
                        assigned = rule.get('set_other_to')
                        if not _intercolumn_values_equal(working.get(other.field_key), assigned):
                            working[other.field_key] = assigned
                            changed_keys.add(other.field_key)
                            changed = True

        # Workflow routing remains authoritative: once a row is in any routed or
        # terminal workflow, automatic disposal must be off. Treat that invariant
        # as part of the fixed-point calculation so rules can react to the final No.
        workflow = str(working.get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY) or '').strip()
        if workflow in TERMINAL_PROBLEM_STATUSES and not _intercolumn_values_equal(
                working.get(SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY), DISPOSE_AUTOMATICALLY_NO):
            working[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
            changed_keys.add(SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY)
            changed = True

        if not changed:
            return working, changed_keys

    raise ValidationError('Intercolumn Value Controller rules did not converge. Check for conflicting two-way rules.')


class ProblemContainer(models.Model):
    """Physical/logical container used to group problem samples."""
    id = models.BigAutoField(primary_key=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_containers_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    disposed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    disposed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_containers_disposed'
    )
    disposal_snapshot = models.JSONField(
        default=dict, blank=True,
        help_text='Rollback state captured immediately before the current container disposal.',
    )

    class Meta:
        ordering = ['-id']

    @property
    def container_id(self):
        return f'PC-{self.id:06d}'

    @classmethod
    def resolve_identifier(cls, value):
        text = str(value or '').strip().upper()
        if not text:
            return None
        if text.startswith('PC-'):
            text = text[3:]
        elif text.startswith('PC'):
            text = text[2:]
        text = text.strip().lstrip('#')
        if not text.isdigit():
            return None
        return cls.objects.filter(pk=int(text)).first()

    def __str__(self):
        return self.container_id


class PreparedProblemSample(models.Model):
    """A reserved ID and tracking link; no problem sample exists until staff decides."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    table = models.ForeignKey(ProblemTable, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    problem_number = models.PositiveBigIntegerField()
    tracking_token = models.CharField(max_length=128)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_problem = models.ForeignKey('ProblemSample', null=True, blank=True, on_delete=models.SET_NULL)


class ProblemSample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    table = models.ForeignKey(ProblemTable, null=True, blank=True, on_delete=models.CASCADE, related_name='problem_samples')
    problem_number = models.PositiveBigIntegerField(editable=False, db_index=True)
    container = models.ForeignKey(
        ProblemContainer, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_samples'
    )
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text='ID from legacy/exported system')
    status = models.CharField(max_length=80, blank=True, db_index=True, default=PROBLEM_STATUS_DEFAULT)
    current_workflow = models.CharField(max_length=80, db_index=True, default=CURRENT_WORKFLOW_DEFAULT)
    als_tracking_number = models.CharField(max_length=150, blank=True, db_index=True)
    problem_sample_count = models.PositiveIntegerField(null=True, blank=True)
    brand = models.CharField(max_length=200, blank=True)
    distributor = models.CharField(max_length=250, blank=True, db_index=True)
    end_user = models.CharField(max_length=250, blank=True, db_index=True)
    date_received = models.DateField(null=True, blank=True, db_index=True)
    problem_type = models.CharField(max_length=250, blank=True, db_index=True)
    issue_description = models.TextField(blank=True)
    client_contact_email = models.EmailField(blank=True, db_index=True)
    courier = models.CharField(max_length=150, blank=True)
    courier_tracking_number = models.CharField(max_length=200, blank=True, db_index=True)
    notify = models.BooleanField(default=False)
    email_confirmation = models.BooleanField(default=False)
    customer_notified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    automatic_disposal_started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    pending_tracking_token = models.CharField(max_length=128, default=None, editable=False, null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True, db_index=True)
    acknowledgement_status_changed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    back_to_testing_notified_at = models.DateTimeField(null=True, blank=True)
    customer_acknowledgement_action = models.CharField(
        max_length=20, choices=CUSTOMER_ACTION_CHOICES, blank=True, db_index=True,
        help_text='Optional follow-up action selected by the customer from the problem sample tracking link.',
    )
    custom_values = models.JSONField(default=dict, blank=True)
    legacy_created_by = models.CharField(max_length=200, blank=True)
    legacy_modified_by = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_samples_created')
    modified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_samples_modified')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_received', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['table', 'problem_number'], name='unique_problem_number_per_table'),
            models.CheckConstraint(
                condition=models.Q(container__isnull=True) | ~models.Q(current_workflow__in=[PROBLEM_STATUS_SHIPPED_BACK, PROBLEM_STATUS_BACK_TO_TESTING]),
                name='no_container_for_shipped_or_testing',
            ),
        ]

    @property
    def dispose_automatically(self):
        value = (self.custom_values or {}).get(SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY)
        if isinstance(value, bool):
            return value
        return str(value or '').strip().casefold() == DISPOSE_AUTOMATICALLY_YES.casefold()

    @property
    def expires_at(self):
        # Automatic-disposal expiration is controlled by the dedicated built-in
        # Dispose Automatically field, independently of Status.
        if not self.dispose_automatically:
            return None
        anchor = self.automatic_disposal_started_at
        if not anchor or not self.table_id:
            return None
        pt_days = getattr(self.table, 'pt_days', 30)
        return anchor + timedelta(days=pt_days)

    @property
    def expiration_status(self):
        expires_at = self.expires_at
        if expires_at and timezone.now() >= expires_at:
            return 'expired'
        return 'active'

    @property
    def workflow_status(self):
        value = (self.custom_values or {}).get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY)
        if value in (None, ''):
            value = self.current_workflow
        value = str(value or '').strip()
        return value if value in CURRENT_WORKFLOW_CHOICES else CURRENT_WORKFLOW_DEFAULT

    def set_workflow_status(self, value):
        """Synchronize the dynamic Current Workflow value and core indexed field."""
        value = str(value or '').strip()
        if value not in CURRENT_WORKFLOW_CHOICES:
            raise ValueError(f'Invalid Current Workflow: {value}')
        values = dict(self.custom_values or {})
        values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = value
        self.custom_values = values
        self.current_workflow = value
        return value

    @property
    def days_until_automatic_disposal(self):
        """Whole days remaining before Current Workflow changes to To be Disposed.

        None means Dispose Automatically is No. Zero means the transition is due now.
        The countdown restarts whenever Dispose Automatically changes from No to Yes.
        """
        if not self.dispose_automatically:
            return None
        expires_at = self.expires_at
        if expires_at is None:
            return None
        return max(0, math.ceil((expires_at - timezone.now()).total_seconds() / 86400))

    @property
    def tracking_link_record_or_none(self):
        """Return the separate tracking-link row without raising when absent."""
        return getattr(self, 'tracking_link_record', None)

    @property
    def acknowledgement_token(self):
        """Backward-compatible alias for the token now stored in ProblemTrackingLink."""
        record = self.tracking_link_record_or_none
        return record.tracking_token if record else None

    @property
    def tracking_link_expires_at(self):
        """When the persisted tracking link becomes inaccessible.

        The actual expiration timestamp is stored on the separate tracking-link
        table. acknowledgement_status_changed_at remains only as the lifecycle
        anchor needed to preserve existing workflow behavior when a link is first
        created after a protected workflow transition.
        """
        record = self.tracking_link_record_or_none
        return record.expires_at if record else None

    @property
    def tracking_link_expired(self):
        expires_at = self.tracking_link_expires_at
        return bool(expires_at and timezone.now() >= expires_at)

    def expected_tracking_link_expiration(self):
        """Return the expiration implied by the current lifecycle anchor."""
        anchor = self.acknowledgement_status_changed_at
        if not anchor or self.workflow_status not in TRACKING_LINK_EXPIRING_STATUSES:
            return None
        return anchor + timedelta(days=TRACKING_LINK_DAYS)

    def set_tracking_link_expiration(self, expires_at):
        """Synchronize the separate tracking-link row when one exists."""
        record = self.tracking_link_record_or_none
        if not record or record.expires_at == expires_at:
            return False
        record.expires_at = expires_at
        record.save(update_fields=['expires_at'])
        return True

    # Backward-compatible property names for older code/API aliases.
    @property
    def acknowledgement_link_expires_at(self):
        return self.tracking_link_expires_at

    @property
    def acknowledgement_link_expired(self):
        return self.tracking_link_expired

    @classmethod
    def purge_expired_acknowledgement_credentials(cls, *, now=None):
        """Legacy no-op: tracking links are persistent and are never purged."""
        return 0

    def purge_acknowledgement_credentials_if_expired(self, *, now=None):
        """Legacy no-op: an expired tracking token remains stored on the row."""
        return False

    def apply_intercolumn_value_controllers(self, *, strict=False):
        """Apply table-defined rules and synchronize indexed built-ins.

        Interactive row saves validate rules strictly before persistence. System
        workflow transitions use non-strict mode so a future data-specific rule
        conflict cannot block disposal/shipping/testing lifecycle operations.
        """
        if not self.table_id:
            return set()
        try:
            values, changed = apply_intercolumn_rules_to_values(self.table, self.custom_values or {})
        except ValidationError:
            if strict:
                raise
            return set()
        if not changed:
            return set()
        self.custom_values = values
        if 'status' in changed:
            self.status = str(values.get('status') or self.status or PROBLEM_STATUS_DEFAULT)
        if SYSTEM_CURRENT_WORKFLOW_FIELD_KEY in changed:
            workflow = str(values.get(SYSTEM_CURRENT_WORKFLOW_FIELD_KEY) or '').strip()
            if workflow in CURRENT_WORKFLOW_CHOICES:
                self.current_workflow = workflow
        return changed

    def apply_acknowledgement_status_transition(
        self, previous_status, *, previous_dispose_automatically=None, changed_at=None, strict_intercolumn=False
    ):
        """Update automatic-disposal and tracking-link lifecycle state.

        Current Workflow controls routing/link-expiry behavior. Dispose Automatically
        controls the automatic-disposal countdown and customer-response reset cycle.
        """
        controller_changes = self.apply_intercolumn_value_controllers(strict=strict_intercolumn)
        controller_update_fields = []
        if controller_changes:
            controller_update_fields.append('custom_values')
            if 'status' in controller_changes:
                controller_update_fields.append('status')
            if SYSTEM_CURRENT_WORKFLOW_FIELD_KEY in controller_changes:
                controller_update_fields.append('current_workflow')

        current_status = self.workflow_status
        current_auto = self.dispose_automatically
        previous_auto = current_auto if previous_dispose_automatically is None else bool(previous_dispose_automatically)
        status_changed = current_status != previous_status
        auto_changed = current_auto != previous_auto
        if not status_changed and not auto_changed:
            return controller_update_fields

        changed_at = changed_at or timezone.now()
        update_fields = list(controller_update_fields)

        # Enabling automatic disposal always starts a fresh disposal countdown
        # and opens a fresh customer-response cycle.
        if current_auto and not previous_auto:
            self.automatic_disposal_started_at = changed_at
            update_fields.append('automatic_disposal_started_at')
            if self.acknowledged_at is not None:
                self.acknowledged_at = None
                update_fields.append('acknowledged_at')
            if self.customer_acknowledgement_action:
                self.customer_acknowledgement_action = ''
                update_fields.append('customer_acknowledgement_action')

        # Protected workflow states start/reset the 30-day tracking-link window.
        # Returning to an active follow-up workflow makes the link accessible again,
        # regardless of the Dispose Automatically value.
        if status_changed:
            if self.back_to_testing_notified_at is not None:
                self.back_to_testing_notified_at = None
                update_fields.append('back_to_testing_notified_at')
            if current_status in TRACKING_LINK_EXPIRING_STATUSES:
                self.acknowledgement_status_changed_at = changed_at
                update_fields.append('acknowledgement_status_changed_at')
                self.set_tracking_link_expiration(changed_at + timedelta(days=TRACKING_LINK_DAYS))
            else:
                if self.acknowledgement_status_changed_at is not None:
                    self.acknowledgement_status_changed_at = None
                    update_fields.append('acknowledgement_status_changed_at')
                self.set_tracking_link_expiration(None)

        if not current_auto and previous_auto and self.customer_acknowledgement_action:
            self.customer_acknowledgement_action = ''
            update_fields.append('customer_acknowledgement_action')

        return update_fields

    def transition_to_disposal_if_due(self, *, now=None, record_history=True):
        """Persist an expired automatic-disposal countdown as To be Disposed.

        Returns True only when this call performs the transition. The method is
        idempotent and deliberately refuses to override any protected workflow
        status such as shipping, back-to-testing, disposed, or already queued
        for disposal.
        """
        now = now or timezone.now()
        previous_status = self.workflow_status
        if previous_status in TERMINAL_PROBLEM_STATUSES:
            return False
        if not self.dispose_automatically:
            return False
        expires_at = self.expires_at
        if expires_at is None or now < expires_at:
            return False

        values = dict(self.custom_values or {})
        values[SYSTEM_CURRENT_WORKFLOW_FIELD_KEY] = PROBLEM_STATUS_TO_BE_DISPOSED
        values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
        self.custom_values = values
        self.current_workflow = PROBLEM_STATUS_TO_BE_DISPOSED
        self.modified_at = now

        # The workflow transition is effective at the deadline itself, even if
        # the first request after that deadline arrives later. In particular,
        # the 30-day tracking-link window starts from the true due time.
        effective_at = expires_at
        update_fields = ['custom_values', 'current_workflow', 'modified_at']
        update_fields.extend(
            self.apply_acknowledgement_status_transition(
                previous_status,
                previous_dispose_automatically=True,
                changed_at=effective_at,
            )
        )
        self.save(update_fields=list(dict.fromkeys(update_fields)))

        # Keep a dedicated analytics event using the true expiry timestamp rather
        # than the later time at which a request/background check noticed it.
        # The ticket/effective-at uniqueness constraint makes this idempotent.
        AutomaticDisposalExpiryEvent.objects.get_or_create(
            ticket=self,
            effective_at=effective_at,
        )

        if record_history:
            ProblemHistory.objects.create(
                problem=self,
                action=ProblemHistory.ACTION_UPDATED,
                actor=None,
                summary='Automatic disposal period ended',
                details={
                    'automatic': True,
                    'reason': 'Automatic disposal period expired',
                    'effective_at': effective_at.isoformat(),
                    'changes': [
                        {
                            'field': 'Current Workflow',
                            'before': previous_status,
                            'after': PROBLEM_STATUS_TO_BE_DISPOSED,
                        },
                        {
                            'field': 'Dispose Automatically',
                            'before': DISPOSE_AUTOMATICALLY_YES,
                            'after': DISPOSE_AUTOMATICALLY_NO,
                        },
                    ],
                },
            )
        return True

    @property
    def is_disposal_eligible(self):
        # Automatic-disposal expiry is persisted as a real transition to
        # To be Disposed. Container disposal therefore relies on the workflow
        # Current Workflow itself, not a hidden alternate eligibility path.
        return self.workflow_status == PROBLEM_STATUS_TO_BE_DISPOSED

    def __str__(self):
        return f'Problem #{self.problem_number}'


class ProblemTrackingLink(models.Model):
    """Persisted public tracking credentials for exactly one problem-sample ticket."""
    ticket = models.OneToOneField(
        ProblemSample,
        on_delete=models.CASCADE,
        related_name='tracking_link_record',
    )
    tracking_token = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'problem_samples_tracking_link'

    def __str__(self):
        return f'Tracking link for ticket #{self.ticket.problem_number}'


class OldTicketDefinition(models.Model):
    """The single tracker-wide age threshold for an old ticket, in calendar months."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    age_months = models.PositiveSmallIntegerField(
        default=24, validators=[MinValueValidator(1), MaxValueValidator(1200)],
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='old_ticket_definitions_updated',
    )

    class Meta:
        db_table = 'problem_samples_old_ticket_definition'


class AutomaticDisposalExpiryEvent(models.Model):
    """Analytics event for an automatic-disposal deadline that moved a ticket."""
    ticket = models.ForeignKey(
        ProblemSample,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='automatic_disposal_expiry_events',
    )
    effective_at = models.DateTimeField(db_index=True)
    date_created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'problem_samples_automatic_disposal_expiry_event'
        constraints = [
            models.UniqueConstraint(
                fields=['ticket', 'effective_at'],
                name='unique_auto_disposal_expiry_per_ticket_deadline',
            ),
        ]
        ordering = ['effective_at', 'id']

    def __str__(self):
        if self.ticket_id:
            return f'Automatic disposal expiry for ticket #{self.ticket.problem_number}'
        return f'Automatic disposal expiry at {self.effective_at.isoformat()}'


class ProblemComment(models.Model):
    problem = models.ForeignKey(ProblemSample, on_delete=models.CASCADE, related_name='comments')
    body = models.TextField()
    author = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    legacy_author = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class ProblemImage(models.Model):
    problem = models.ForeignKey(ProblemSample, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='problem-images/%Y/%m/', blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    include_in_customer_notification = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class ProblemAttachment(models.Model):
    problem = models.ForeignKey(ProblemSample, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='problem-attachments/%Y/%m/')
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=160, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    include_in_customer_notification = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return self.original_name or self.file.name


class PublicTrackingRateBucket(models.Model):
    """Database-shared request counters for unauthenticated tracking endpoints."""

    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class NotificationRecipient(models.Model):
    """The shared destination for Edmonton operations emails."""

    key = models.CharField(max_length=80, primary_key=True)
    email = models.EmailField(max_length=254)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='notification_recipients_updated'
    )
    updated_at = models.DateTimeField(auto_now=True)


class EmailTemplate(models.Model):
    """Administrator-editable email copy used by the tracker."""

    CUSTOMER_NOTIFICATION = 'customer_notification'

    key = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    subject_template = models.CharField(max_length=500)
    body_template = models.TextField()
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='email_templates_updated'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'key']

    def __str__(self):
        return self.name


class ProblemHistory(models.Model):
    ACTION_CREATED = 'created'
    ACTION_UPDATED = 'updated'
    ACTION_COMMENT = 'comment'
    ACTION_CUSTOMER_NOTIFICATION = 'customer_notification'
    ACTION_ACKNOWLEDGED = 'acknowledged'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'Created'),
        (ACTION_UPDATED, 'Saved changes'),
        (ACTION_COMMENT, 'Added comment'),
        (ACTION_CUSTOMER_NOTIFICATION, 'Customer notification sent'),
        (ACTION_ACKNOWLEDGED, 'Customer acknowledged problem sample'),
    ]

    problem = models.ForeignKey(ProblemSample, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.problem} - {self.get_action_display()}'


@receiver(post_delete, sender=ProblemImage)
def delete_problem_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_delete, sender=ProblemAttachment)
def delete_problem_attachment_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
