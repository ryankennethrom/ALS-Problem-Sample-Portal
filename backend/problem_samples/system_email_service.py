"""Generate reviewable monthly Distributor emails. This module NEVER sends email."""
from collections import Counter
from datetime import date, datetime, time, timedelta
import re
import uuid
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ProblemColumn, ProblemSample, SystemEmail


def distributor_matches(value, rule):
    name = str(value or '').strip().casefold()
    pattern = str(rule.get('pattern') or '').strip().casefold()
    if not name or not pattern:
        return False
    match_type = rule.get('match_type')
    if match_type == 'exact':
        return name == pattern
    if match_type == 'contains':
        return pattern in name
    if match_type == 'starts_with':
        return name.startswith(pattern)
    if match_type == 'ends_with':
        return name.endswith(pattern)
    if match_type == 'wildcard':
        return re.fullmatch(re.escape(pattern).replace(r'\*', '.*').replace(r'\?', '.'), name) is not None
    return False


def previous_month(today=None):
    today = today or timezone.localdate()
    first_this_month = today.replace(day=1)
    first_last_month = (first_this_month - timedelta(days=1)).replace(day=1)
    return first_last_month, first_this_month


def normalize_addresses(values):
    addresses = []
    seen = set()
    for item in values if isinstance(values, list) else []:
        email = str(item or '').strip()
        if email and email.casefold() not in seen:
            addresses.append(email)
            seen.add(email.casefold())
    return addresses


def create_monthly_report(column, rule, start, end, ticket_rows):
    """Snapshot the selected tickets into an email draft for a single matching rule."""
    matches = []
    for row in ticket_rows:
        raw = (row.custom_values or {}).get(column.field_key)
        if raw in ('', None) and column.field_key == 'distributor':
            raw = row.distributor
        if distributor_matches(raw, rule):
            matches.append(row)

    month_label = start.strftime('%B %Y')
    table_name = column.table.name
    count = len(matches)
    workflow_counts = Counter(row.current_workflow for row in matches)
    pattern = rule['pattern']
    link_root = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    subject = f'ALS Edmonton Monthly Problem Sample Report — {table_name} — {month_label}'
    lines = [
        'Hello,', '',
        f'Please find the monthly problem sample report for {month_label}.',
        f'Table: {table_name}',
        f'Distributor filter ({rule["match_type"]}): {pattern}',
        f'Report period: {start.isoformat()} through {(end - timedelta(days=1)).isoformat()} (Edmonton time)',
        'Scope: tickets created during the report period whose Distributor matches this rule.',
        f'Total matching tickets: {count}', '',
        'Current workflow breakdown (at report generation):',
    ]
    for workflow, amount in sorted(workflow_counts.items()):
        lines.append(f'- {workflow}: {amount}')
    if not count:
        lines.append('- No matching tickets for this month.')
    else:
        lines.extend(['', 'Matching tickets (up to 5 shown):'])
        for row in matches[:5]:
            track = f' | ALS Tracking: {row.als_tracking_number}' if row.als_tracking_number else ''
            link = f'{link_root}/problems/{row.id}' if link_root else f'/problems/{row.id}'
            lines.extend([f'- Ticket #{row.problem_number}: {row.current_workflow}{track}', f'  {link}'])
        if count > 5:
            lines.append(f'And {count - 5} additional matching ticket(s).')
    lines.extend(['', 'These figures are a snapshot of the tracker at report preparation, not a live dashboard.',
                  'This report was prepared by the ALS Edmonton Ticket Tracker and reviewed by a staff member before sending.'])
    return {
        'period_end': end, 'distributor_pattern': pattern,
        'to_emails': normalize_addresses(rule.get('cc_emails')),
        'subject': subject, 'body': '\n'.join(lines), 'matched_ticket_count': count,
    }


def queue_due_monthly_reports(today=None):
    """Idempotently queue last month's enabled rules; safe for repeated cron runs.

    Never emails anyone. Invoke daily via Railway Cron or with the management command.
    """
    start, end = previous_month(today)
    zone = ZoneInfo(settings.TIME_ZONE)
    low = timezone.make_aware(datetime.combine(start, time.min), zone)
    high = timezone.make_aware(datetime.combine(end, time.min), zone)
    created = 0
    examined = 0
    # Query per table only once; use table+column selection to prevent cross-table data leakage.
    table_tickets = {}
    for column in ProblemColumn.objects.filter(column_type=ProblemColumn.TYPE_DISTRIBUTOR).select_related('table'):
        rules = column.distributor_cc_rules or []
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or rule.get('send_monthly_reports') is not True:
                continue
            if not rule.get('pattern') or not normalize_addresses(rule.get('cc_emails')):
                continue
            # A newly enabled rule should not queue reports for periods that
            # ended before it was enabled (for example September on October 19).
            enabled_at = rule.get('monthly_reports_enabled_at')
            if enabled_at:
                try:
                    started_at = datetime.fromisoformat(enabled_at)
                    if (started_at.astimezone(zone) if started_at.tzinfo else started_at.replace(tzinfo=zone)).date() >= end:
                        continue
                except (TypeError, ValueError):
                    continue
            identifier = rule.get('id')
            try:
                rule_id = uuid.UUID(str(identifier))
            except (ValueError, TypeError, AttributeError):
                # For rows created without validated serializers; stable until next configuration save.
                rule_id = uuid.uuid5(uuid.NAMESPACE_URL, f'{column.id}:{index}:{rule.get("pattern")}')
            if SystemEmail.objects.filter(source_column=column, rule_identifier=rule_id, period_start=start).exists():
                continue
            examined += 1
            if column.table_id not in table_tickets:
                table_tickets[column.table_id] = list(
                    ProblemSample.objects.filter(table_id=column.table_id, created_at__gte=low, created_at__lt=high)
                    .only('id', 'problem_number', 'custom_values', 'distributor', 'current_workflow', 'als_tracking_number')
                    .order_by('problem_number')
                )
            draft = create_monthly_report(column, rule, start, end, table_tickets[column.table_id])
            with transaction.atomic():
                _, was_created = SystemEmail.objects.get_or_create(
                    source_column=column, rule_identifier=rule_id, period_start=start,
                    defaults={'email_type': SystemEmail.TYPE_DISTRIBUTOR_MONTHLY, **draft},
                )
            created += int(was_created)
    return {'created': created, 'examined': examined, 'period_start': start.isoformat(), 'period_end': end.isoformat()}
