import uuid
import secrets
import math
from datetime import timedelta
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models.signals import post_delete
from django.dispatch import receiver


PROBLEM_STATUS_AUTOMATICALLY_DISPOSED = 'Automatically Disposed'
PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL = 'Halted Automatic Disposal'
PROBLEM_STATUS_TO_BE_DISPOSED = 'To be Disposed'
PROBLEM_STATUS_TO_BE_SHIPPED_BACK = 'To be shipped back to client'
PROBLEM_STATUS_TO_BE_BACK_TO_TESTING = 'To be back to testing'
PROBLEM_STATUS_BACK_TO_TESTING = 'Back to testing'
PROBLEM_STATUS_DISPOSED = 'Disposed'
PROBLEM_STATUS_SHIPPED_BACK = 'Shipped back to client'

CUSTOMER_ACTION_DISPOSE = 'dispose'
CUSTOMER_ACTION_SHIP_BACK = 'ship_back'
CUSTOMER_ACTION_HOLD = 'hold'
CUSTOMER_ACTION_REQUESTED_INFORMATION = 'requested_info'
CUSTOMER_ACTION_CHOICES = [
    (CUSTOMER_ACTION_DISPOSE, 'Dispose Sample(s)'),
    (CUSTOMER_ACTION_SHIP_BACK, 'Ship back samples'),
    (CUSTOMER_ACTION_HOLD, 'Hold sample'),
    (CUSTOMER_ACTION_REQUESTED_INFORMATION, 'Fill out requested information (if applicable)'),
]

SYSTEM_PROBLEM_STATUSES = [
    PROBLEM_STATUS_AUTOMATICALLY_DISPOSED,
    PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL,
    PROBLEM_STATUS_TO_BE_DISPOSED,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_BACK_TO_TESTING,
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_SHIPPED_BACK,
]

TRACKING_LINK_DAYS = 30
TRACKING_LINK_EXPIRING_STATUSES = {
    PROBLEM_STATUS_TO_BE_DISPOSED,
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    PROBLEM_STATUS_SHIPPED_BACK,
    PROBLEM_STATUS_TO_BE_BACK_TO_TESTING,
    PROBLEM_STATUS_BACK_TO_TESTING,
}
# Legacy aliases kept so historical code/migrations and older clients remain compatible.
ACKNOWLEDGEMENT_LINK_DAYS = TRACKING_LINK_DAYS
ACKNOWLEDGEMENT_EXPIRING_STATUSES = TRACKING_LINK_EXPIRING_STATUSES
ACKNOWLEDGEMENT_PRE_ACK_STATUSES = {PROBLEM_STATUS_AUTOMATICALLY_DISPOSED}

SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY = 'system-days-until-automatic-disposal'
SYSTEM_TRACKING_LINK_FIELD_KEY = 'system-tracking-link'
SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY = 'system-tracking-link-expiry'


def generate_acknowledgement_token():
    """Return a high-entropy URL-safe token for public problem-sample tracking links."""
    return secrets.token_urlsafe(48)


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
        help_text='Automatic-disposal expiration period in days from the most recent transition into Automatically Disposed. Zero means immediate eligibility when automatic disposal is activated.',
    )
    acknowledgement_link_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(3650)],
        help_text='How many days an acknowledged customer link continues to show the acknowledgement confirmation.',
    )
    def status_choices(self):
        return list(SYSTEM_PROBLEM_STATUSES)

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


class ProblemSample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    table = models.ForeignKey(ProblemTable, null=True, blank=True, on_delete=models.CASCADE, related_name='problem_samples')
    problem_number = models.PositiveBigIntegerField(editable=False, db_index=True)
    container = models.ForeignKey(
        ProblemContainer, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_samples'
    )
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text='ID from legacy/exported system')
    status = models.CharField(max_length=80, blank=True, db_index=True, default=PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL)
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
    acknowledgement_token = models.CharField(max_length=128, default=None, editable=False, unique=True, null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True, db_index=True)
    acknowledgement_status_changed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    customer_acknowledgement_action = models.CharField(
        max_length=20, choices=CUSTOMER_ACTION_CHOICES, blank=True, db_index=True,
        help_text='Optional follow-up action selected by the customer from the problem sample tracking link.',
    )
    custom_values = models.JSONField(default=dict, blank=True)
    legacy_created_by = models.CharField(max_length=200, blank=True)
    legacy_modified_by = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_samples_created')
    modified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='problem_samples_modified')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_received', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['table', 'problem_number'], name='unique_problem_number_per_table'),
        ]

    @property
    def expires_at(self):
        # Automatic-disposal expiration is anchored to the most recent transition
        # into Automatically Disposed. Outside that status there is no active
        # automatic-disposal expiration date.
        if self.workflow_status != PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
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
        value = (self.custom_values or {}).get('status')
        if value in (None, ''):
            value = self.status
        return str(value or '').strip()

    @property
    def days_until_automatic_disposal(self):
        """Whole days remaining before the automatic-disposal state becomes eligible.

        None means automatic disposal is halted or has never been activated. Zero means the sample is eligible now.
        The countdown restarts whenever Status transitions into Automatically Disposed.
        """
        if self.workflow_status != PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
            return None
        expires_at = self.expires_at
        if expires_at is None:
            return None
        return max(0, math.ceil((expires_at - timezone.now()).total_seconds() / 86400))

    @property
    def tracking_link_expires_at(self):
        """When the persistent tracking link becomes inaccessible.

        The database field name is retained for migration compatibility, but it now
        stores the timestamp of the latest transition into one of the six workflow
        states that start/reset the tracking-link expiry window.
        """
        anchor = self.acknowledgement_status_changed_at
        if not anchor:
            return None
        return anchor + timedelta(days=TRACKING_LINK_DAYS)

    @property
    def tracking_link_expired(self):
        expires_at = self.tracking_link_expires_at
        return bool(expires_at and timezone.now() >= expires_at)

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

    def apply_acknowledgement_status_transition(self, previous_status, *, changed_at=None):
        """Update automatic-disposal and persistent tracking-link lifecycle state."""
        current_status = self.workflow_status
        if current_status == previous_status:
            return []

        changed_at = changed_at or timezone.now()
        update_fields = []

        # Entering Automatically Disposed always starts a fresh disposal countdown.
        if current_status == PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
            self.automatic_disposal_started_at = changed_at
            update_fields.append('automatic_disposal_started_at')

        # The tracking URL itself never changes or gets purged. Entering one of
        # the terminal workflow states starts/resets its 30-day accessibility
        # window. Returning to either active follow-up state makes the same
        # persistent tracking link accessible again by clearing that expiry anchor.
        if current_status in TRACKING_LINK_EXPIRING_STATUSES:
            self.acknowledgement_status_changed_at = changed_at
            update_fields.append('acknowledgement_status_changed_at')
        elif current_status in {
            PROBLEM_STATUS_AUTOMATICALLY_DISPOSED,
            PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL,
        }:
            if self.acknowledgement_status_changed_at is not None:
                self.acknowledgement_status_changed_at = None
                update_fields.append('acknowledgement_status_changed_at')

        # Returning to Automatically Disposed also opens a fresh customer
        # response cycle and restarts the automatic-disposal countdown.
        if current_status == PROBLEM_STATUS_AUTOMATICALLY_DISPOSED:
            if self.acknowledged_at is not None:
                self.acknowledged_at = None
                update_fields.append('acknowledged_at')
            if self.customer_acknowledgement_action:
                self.customer_acknowledgement_action = ''
                update_fields.append('customer_acknowledgement_action')
        elif current_status == PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL:
            if previous_status != PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL and self.customer_acknowledgement_action:
                self.customer_acknowledgement_action = ''
                update_fields.append('customer_acknowledgement_action')

        return update_fields

    @property
    def is_disposal_eligible(self):
        status = self.workflow_status
        return (
            status == PROBLEM_STATUS_TO_BE_DISPOSED
            or (
                status == PROBLEM_STATUS_AUTOMATICALLY_DISPOSED
                and self.expiration_status == 'expired'
            )
        )

    def __str__(self):
        return f'Problem #{self.problem_number}'


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
