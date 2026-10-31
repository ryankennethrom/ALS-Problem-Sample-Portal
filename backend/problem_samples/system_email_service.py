"""Generate reviewable monthly Brand emails. This module NEVER sends email."""
from collections import Counter
from datetime import date, datetime, time, timedelta
import re
import uuid
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ProblemColumn, ProblemSample, SystemEmail
from accounts.models import Lab


from .brand_email_rules import rule_matches
from .monthly_report_portal import snapshot_tickets, finalize_report, REPORT_LIFETIME_DAYS


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


def create_monthly_report(column, rule, start, end, ticket_rows, *, as_of=None, lab=None):
    """Snapshot the selected tickets into an email draft for a single matching rule."""
    matches = []
    company_cache = {}
    for row in ticket_rows:
        if rule_matches(column, row.custom_values or {}, rule, company_cache=company_cache):
            matches.append(row)

    month_label = start.strftime('%B %Y')
    count = len(matches)
    pattern = rule['pattern']
    lab_name = lab.name if lab else 'Edmonton'
    subject = f'ALS {lab_name} {"Month-to-Date" if as_of else "Monthly"} Problem Sample Report — {column.table.name} — {month_label}'
    return {
        'period_end': end, 'distributor_pattern': pattern,
        'to_emails': normalize_addresses(rule.get('cc_emails')),
        'subject': subject, 'body': 'Report link is being prepared.', 'matched_ticket_count': count,
        'public_expires_at': timezone.now() + timedelta(days=REPORT_LIFETIME_DAYS),
        'report_snapshot': snapshot_tickets(column, rule, start, end, matches, lab),
    }


def queue_manual_monthly_report(column, rule, *, request_identifier, now=None, lab=None):
    """Prepare an immediately reviewable month-to-date draft; never send mail.

    Manual requests do not consume the unique scheduled report for this month.
    The caller must validate permissions and select a persisted enabled rule.
    """
    now = now or timezone.now()
    zone = ZoneInfo(settings.TIME_ZONE)
    local_now = now.astimezone(zone)
    start = local_now.date().replace(day=1)
    end = local_now.date() + timedelta(days=1)  # exclusive display boundary
    low = timezone.make_aware(datetime.combine(start, time.min), zone)
    if lab is None:
        raise ValueError('Select a lab before preparing the monthly report.')
    rows = list(ProblemSample.objects.filter(
        lab=lab, table_id=column.table_id, created_at__gte=low, created_at__lte=now,
    ).select_related('container__lab').order_by('problem_number'))
    draft = create_monthly_report(column, rule, start, end, rows, as_of=local_now, lab=lab)
    rule_id = uuid.UUID(str(rule['id']))
    # The same request UUID can be retried safely after network errors.
    with transaction.atomic():
        mail, created = SystemEmail.objects.get_or_create(
            request_identifier=request_identifier,
            defaults={
                'lab': lab,
                'email_type': SystemEmail.TYPE_DISTRIBUTOR_MONTHLY,
                'source_column': column,
                'rule_identifier': rule_id,
                'period_start': start,
                'generation_mode': SystemEmail.GENERATION_MANUAL,
                **draft,
            },
        )
        if created:
            finalize_report(mail)
    if mail.lab_id != lab.pk or mail.source_column_id != column.id or mail.rule_identifier != rule_id or mail.generation_mode != SystemEmail.GENERATION_MANUAL:
        raise ValueError('This request identifier was already used for a different monthly report.')
    return mail, created


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
    for column in ProblemColumn.objects.filter(column_type=ProblemColumn.TYPE_BRAND).select_related('table'):
      for lab in Lab.objects.all():
          rules = column.brand_cc_rules or []
          for index, rule in enumerate(rules):
              if not isinstance(rule, dict) or rule.get('pending_brand_review') or rule.get('send_monthly_reports') is not True:
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
              if SystemEmail.objects.filter(lab=lab, source_column=column, rule_identifier=rule_id, period_start=start,
                                           generation_mode=SystemEmail.GENERATION_SCHEDULED).exists():
                  continue
              examined += 1
              if (lab.id, column.table_id) not in table_tickets:
                  table_tickets[(lab.id, column.table_id)] = list(
                      ProblemSample.objects.filter(lab=lab, table_id=column.table_id, created_at__gte=low, created_at__lt=high)
                      .select_related('container__lab')
                      .order_by('problem_number')
                  )
              draft = create_monthly_report(column, rule, start, end, table_tickets[(lab.id, column.table_id)], lab=lab)
              with transaction.atomic():
                  mail, was_created = SystemEmail.objects.get_or_create(
                      lab=lab, source_column=column, rule_identifier=rule_id, period_start=start,
                      generation_mode=SystemEmail.GENERATION_SCHEDULED,
                      defaults={'email_type': SystemEmail.TYPE_DISTRIBUTOR_MONTHLY, **draft},
                  )
                  if was_created:
                      finalize_report(mail)
              created += int(was_created)
    return {'created': created, 'examined': examined, 'period_start': start.isoformat(), 'period_end': end.isoformat()}
