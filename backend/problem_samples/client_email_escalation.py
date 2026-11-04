"""Automatic, idempotent promotion to the next Client Email dependency.

Runs on application requests (not cron). Never sends mail or changes tracking tokens.
"""
from datetime import timedelta
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from customers.models import Customer
from .models import (
    ProblemSample, ProblemColumn, ProblemHistory,
    CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER, SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY, DISPOSE_AUTOMATICALLY_NO, DISPOSE_AUTOMATICALLY_YES,
)


def _emails_for_company(company):
    if not company:
        return []
    qs = Customer.objects.filter(company_name__iexact=company).exclude(email='').order_by('id').values_list('email', flat=True)
    found, seen = [], set()
    for item in qs:
        email = str(item or '').strip()
        if email and email.lower() not in seen:
            found.append(email)
            seen.add(email.lower())
    return found


def _infer_legacy_priority(dependencies, values, field_key, *, emails_for_company):
    """Estimate which list received a legacy tracking-link email.

    Old send-history entries do not record the selected dependency priority.
    Count distinct saved Client Email addresses that also belong to each
    *populated* dependency's Customer Export email list. Use the priority with
    the highest overlap. On a tie, use priority 1 when it has a populated
    email list; if priority 1 is empty, use the first populated tied list.

    Empty company fields and company lists with no email addresses do not
    participate in the comparison. With no saved emails or no populated
    dependencies, no historical priority can be determined.
    """
    stored = values.get(field_key)
    if isinstance(stored, str):
        stored = stored.replace(';', ',').replace('\n', ',').split(',')
    if not isinstance(stored, list):
        return None, False
    saved = {str(item).strip().casefold() for item in stored
             if isinstance(item, str) and item.strip()}
    if not saved:
        return None, False

    scores = {}
    for position, dependency in enumerate(dependencies):
        company = str(values.get(dependency.field_key) or '').strip()
        if not company:
            continue
        known = {str(email).strip().casefold() for email in emails_for_company(company)
                 if str(email or '').strip()}
        if known:  # Empty priority lists cannot win, even a zero-score tie.
            scores[position] = len(saved & known)

    if not scores:
        return None, False
    best_score = max(scores.values())
    winners = [position for position, score in scores.items() if score == best_score]
    if len(winners) == 1:
        return winners[0], best_score > 0
    # Explicit user preference: all ties fall back to Priority 1, provided
    # it has a usable email list; otherwise prefer the earliest tied list.
    return (0 if 0 in scores else winners[0]), False


def try_escalate_ticket(ticket, *, now, columns=None, dependency_map=None):
    """Must be invoked under a select_for_update row lock."""
    if ticket.workflow_status != CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER or not ticket.client_email_last_tracking_sent_at:
        return False
    last_sent = ticket.client_email_last_tracking_sent_at
    last_response = ticket.client_email_last_customer_response_at
    # A response after the most recent tracking email resets the inactivity clock.
    anchor = max(last_sent, last_response) if last_response else last_sent
    state = dict(ticket.client_email_priority_state or {})
    values = dict(ticket.custom_values or {})
    if columns is None:
        columns = ticket.table.columns.filter(column_type=ProblemColumn.TYPE_CLIENT_EMAIL, client_email_fallback_hours__isnull=False)
    for column in columns:
        dependencies = (dependency_map or {}).get(str(column.id)) or column.ordered_client_email_dependency_columns()
        if len(dependencies) < 2 or now < anchor + timedelta(hours=column.client_email_fallback_hours):
            continue
        known_position = state.get(str(column.id))
        if type(known_position) is int and 0 <= known_position < len(dependencies):
            position, inferred = known_position, False
        else:
            position, inferred = _infer_legacy_priority(
                dependencies, values, column.field_key, emails_for_company=_emails_for_company,
            )
            if position is None:
                # No saved addresses or no populated dependency email lists:
                # never attribute an old tracking send to an empty list.
                continue
        # Find the next usable contact list, without reusing a previous priority.
        for next_position in range(position + 1, len(dependencies)):
            dependency = dependencies[next_position]
            company = str(values.get(dependency.field_key) or '').strip()
            emails = _emails_for_company(company)
            if not emails:
                continue
            previous_label = dependencies[position].name
            reason = (f'{previous_label} has not responded for a while. '
                      f'The client contact email field has been changed to '
                      f'{dependency.name}. Please resend the tracking link.')
            old_emails = values.get(column.field_key, [])
            was_dispose_automatically = ticket.dispose_automatically
            values[column.field_key] = emails
            # A timed-out tracking link must never lead to automatic disposal
            # while staff need to contact the next priority email list.
            # This built-in is stored in custom_values (not a model Boolean).
            values[SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY] = DISPOSE_AUTOMATICALLY_NO
            ticket.custom_values = values
            ticket.set_workflow_status(CURRENT_WORKFLOW_DEFAULT)
            state[str(column.id)] = next_position
            ticket.client_email_priority_state = state
            ticket.save(update_fields=['custom_values', 'current_workflow', 'client_email_priority_state', 'modified_at'])
            changes = [
                {'field': column.name, 'before': old_emails, 'after': emails},
                {'field': 'Current Workflow', 'before': CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
                 'after': CURRENT_WORKFLOW_DEFAULT},
            ]
            if was_dispose_automatically:
                changes.append({'field': 'Dispose Automatically',
                                'before': DISPOSE_AUTOMATICALLY_YES,
                                'after': DISPOSE_AUTOMATICALLY_NO})
            ProblemHistory.objects.create(
                problem=ticket, action=ProblemHistory.ACTION_UPDATED, actor=None,
                summary='Client Email priority escalated; resend tracking link',
                details={'automatic': True, 'reason': reason, 'client_email_column': str(column.id),
                         'changes': changes,
                         'from_priority': position + 1, 'to_priority': next_position + 1,
                         'inferred_original_priority': inferred},
            )
            return True
    return False


def transition_due_client_email_priorities(*, now=None):
    """Check outstanding response timers; row locks make duplicate escalations impossible."""
    now = now or timezone.now()
    configured = list(ProblemColumn.objects.filter(
        column_type=ProblemColumn.TYPE_CLIENT_EMAIL,
        client_email_fallback_hours__isnull=False,
    ))
    if not configured:
        return 0
    by_table = {}
    dependency_map = {}
    for column in configured:
        by_table.setdefault(column.table_id, []).append(column)
        dependency_map[str(column.id)] = column.ordered_client_email_dependency_columns()
    minimum_hours = min(column.client_email_fallback_hours for column in configured)
    # Older imported/restored tickets can have a historical workflow in
    # custom_values without a synchronized indexed current_workflow column.
    # The model's workflow_status property reads custom_values first, so
    # include those rows here as well. The per-ticket check enforces the
    # authoritative workflow again under a row lock.
    waiting = Q(current_workflow=CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER) | Q(**{
        f'custom_values__{SYSTEM_CURRENT_WORKFLOW_FIELD_KEY}': CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
    })
    ids = list(ProblemSample.objects.filter(
        waiting,
        table_id__in=list(by_table),
        client_email_last_tracking_sent_at__lte=now - timedelta(hours=minimum_hours),
    ).values_list('pk', flat=True))
    changed = 0
    for pk in ids:
        with transaction.atomic():
            # ProblemSample.table is nullable. select_related('table') would
            # generate a LEFT OUTER JOIN; PostgreSQL rejects FOR UPDATE on
            # the nullable side of that join. No related table fields are
            # needed here: dependency columns were prefetched above, and
            # the ticket row alone must be locked to prevent duplicate work.
            ticket = ProblemSample.objects.select_for_update(of=('self',)).filter(pk=pk).first()
            if ticket and try_escalate_ticket(ticket, now=now,
                                              columns=by_table.get(ticket.table_id, []),
                                              dependency_map=dependency_map):
                changed += 1
    return changed


def check_client_email_escalations_on_request():
    # A small cooldown prevents needless database scans on each API request.
    key = 'client-email-escalation-check-v1'
    if not cache.add(key, True, timeout=300):
        return 0
    try:
        return transition_due_client_email_priorities()
    except Exception:
        cache.delete(key)
        raise
