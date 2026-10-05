from datetime import datetime, time, timedelta


from django.db.models import BooleanField, Case, Count, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AutomaticDisposalExpiryEvent, ProblemContainer, ProblemHistory, ProblemSample, ProblemTable, ProblemTrackingLink,
    CURRENT_WORKFLOW_DEFAULT, PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_TO_BE_BACK_TO_TESTING, PROBLEM_STATUS_TO_BE_DISPOSED,
    PROBLEM_STATUS_TO_BE_SHIPPED_BACK, TERMINAL_PROBLEM_STATUSES,
)
from .old_tickets import old_ticket_age_months, old_ticket_anniversary, old_ticket_before
from .storage_stats import image_storage_stats

WINDOWS = {
    'day': timedelta(days=1),
    'week': timedelta(days=7),
    'month': timedelta(days=30),
    'six_months': timedelta(days=183),
    'year': timedelta(days=365),
}
CHART_RANGES = {'week', 'month', 'six_months', 'year', 'custom'}

# A person's latest history entry determines ownership. The tracking-link markers
# are the same markers HistorySerializer uses to display the actor as Customer.
CUSTOMER_HISTORY = (
    Q(details__responded_via__in=['public_tracking_link', 'public_acknowledgement_link'])
    | Q(details__acknowledged_via__in=['public_tracking_link', 'public_verification_link'])
)
INELIGIBLE_WORKFLOWS = list(TERMINAL_PROBLEM_STATUSES)


def tracking_not_sent_tickets(queryset=None):
    """CS Follow Up tickets without a persisted customer tracking link."""
    if queryset is None:
        queryset = ProblemSample.objects.all()
    return queryset.filter(
        current_workflow=CURRENT_WORKFLOW_DEFAULT,
        tracking_link_record__isnull=True,
    )


def _latest_person_annotated_tickets(queryset=None):
    if queryset is None:
        queryset = ProblemSample.objects.all()
    latest_person = (
        ProblemHistory.objects.filter(problem_id=OuterRef('pk'))
        .filter(Q(actor_id__isnull=False) | CUSTOMER_HISTORY)
        .filter(Q(details__automatic__isnull=True) | Q(details__automatic=False))
        .order_by('-created_at', '-id')
    )
    latest_person = latest_person.annotate(is_customer=Case(
        When(CUSTOMER_HISTORY, then=Value(True)),
        default=Value(False), output_field=BooleanField(),
    ))
    return queryset.annotate(
        last_response_at=Subquery(latest_person.values('created_at')[:1]),
        last_person_is_customer=Subquery(latest_person.values('is_customer')[:1]),
    )


def _customer_responded_tickets(queryset=None):
    return (
        _latest_person_annotated_tickets(queryset)
        .filter(last_person_is_customer=True)
        .exclude(current_workflow__in=INELIGIBLE_WORKFLOWS)
    )


def customer_service_other_tickets(queryset=None):
    """CS Follow-Up tickets in neither Tracking Not Sent nor New Tracking Link Response."""
    if queryset is None:
        queryset = ProblemSample.objects.all()
    # Tracking Not Sent is exactly CS Follow-Up + no persisted tracking link.
    # Once a link exists, the ticket belongs to New Tracking Link Response only
    # while the latest human history entry is from the customer. Everything
    # else still in CS Follow-Up belongs to Other.
    return (
        _latest_person_annotated_tickets(queryset)
        .filter(current_workflow=CURRENT_WORKFLOW_DEFAULT, tracking_link_record__isnull=False)
        .exclude(last_person_is_customer=True)
    )


def _custom_bounds(start_text, end_text):
    start_date = parse_date(str(start_text or '').strip())
    end_date = parse_date(str(end_text or '').strip())
    if not start_date or not end_date:
        raise ValueError('Custom dates must use YYYY-MM-DD.')
    if end_date < start_date:
        raise ValueError('Custom end date cannot be before the start date.')
    tz = timezone.get_current_timezone()
    start_at = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end_at = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)
    return start_date, end_date, start_at, end_at


def _next_month(value):
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value.replace(month=value.month + 1, day=1)


def _date_label(value):
    return value.strftime('%b %d').replace(' 0', ' ')


def _series(queryset, datetime_field, start_at, end_at, bucket):
    tz = timezone.get_current_timezone()
    trunc = {
        'day': TruncDay(datetime_field, tzinfo=tz),
        'week': TruncWeek(datetime_field, tzinfo=tz),
        'month': TruncMonth(datetime_field, tzinfo=tz),
    }[bucket]
    grouped = (
        queryset
        .filter(**{f'{datetime_field}__gte': start_at, f'{datetime_field}__lt': end_at})
        .annotate(period=trunc)
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )
    counts = {}
    for row in grouped:
        local = timezone.localtime(row['period'], tz)
        if bucket == 'day':
            key = local.date().isoformat()
        elif bucket == 'week':
            d = local.date() - timedelta(days=local.date().weekday())
            key = d.isoformat()
        else:
            key = f'{local.year:04d}-{local.month:02d}'
        counts[key] = int(row['count'])

    first = timezone.localtime(start_at, tz).date()
    last = timezone.localtime(end_at - timedelta(microseconds=1), tz).date()
    points = []
    if bucket == 'day':
        cursor = first
        while cursor <= last:
            key = cursor.isoformat()
            points.append({'period': key, 'label': _date_label(cursor), 'count': counts.get(key, 0)})
            cursor += timedelta(days=1)
    elif bucket == 'week':
        cursor = first - timedelta(days=first.weekday())
        last = last - timedelta(days=last.weekday())
        while cursor <= last:
            key = cursor.isoformat()
            points.append({'period': key, 'label': f'Week of {_date_label(cursor)}', 'count': counts.get(key, 0)})
            cursor += timedelta(days=7)
    else:
        cursor = first.replace(day=1)
        last = last.replace(day=1)
        while cursor <= last:
            key = f'{cursor.year:04d}-{cursor.month:02d}'
            points.append({'period': key, 'label': cursor.strftime('%b %Y'), 'count': counts.get(key, 0)})
            cursor = _next_month(cursor)
    return points


class DashboardView(APIView):
    def get(self, request):
        now = timezone.now()
        selected = str(request.query_params.get('range') or 'week').strip().lower()
        if selected not in CHART_RANGES:
            return Response({'detail': 'Invalid dashboard graph range.'}, status=400)

        start_text = request.query_params.get('start_date')
        end_text = request.query_params.get('end_date')
        custom = None
        if start_text or end_text:
            if not start_text or not end_text:
                return Response({'detail': 'Choose both a custom start date and end date.'}, status=400)
            try:
                custom = _custom_bounds(start_text, end_text)
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=400)

        table_id = str(request.query_params.get('table') or '').strip()
        selected_table = None
        opened_tickets = ProblemSample.objects.all()
        if table_id:
            try:
                selected_table = ProblemTable.objects.get(pk=table_id)
            except (ProblemTable.DoesNotExist, ValueError, TypeError):
                return Response({'detail': 'Ticket table not found.'}, status=404)
            opened_tickets = opened_tickets.filter(table=selected_table)

        opened_counts = opened_tickets.aggregate(
            day=Count('id', filter=Q(created_at__gte=now - WINDOWS['day'])),
            week=Count('id', filter=Q(created_at__gte=now - WINDOWS['week'])),
            month=Count('id', filter=Q(created_at__gte=now - WINDOWS['month'])),
            six_months=Count('id', filter=Q(created_at__gte=now - WINDOWS['six_months'])),
            year=Count('id', filter=Q(created_at__gte=now - WINDOWS['year'])),
        )
        counts = {key: int(value or 0) for key, value in opened_counts.items()}
        action_counts = ProblemSample.objects.aggregate(
            to_be_shipped=Count('id', filter=Q(current_workflow=PROBLEM_STATUS_TO_BE_SHIPPED_BACK)),
            to_be_back_to_testing=Count('id', filter=Q(current_workflow=PROBLEM_STATUS_TO_BE_BACK_TO_TESTING)),
        )
        counts.update({key: int(value or 0) for key, value in action_counts.items()})
        counts['tracking_not_sent'] = tracking_not_sent_tickets().count()
        counts['customer_service_other'] = customer_service_other_tickets().count()
        age_months = old_ticket_age_months()
        counts['old_tickets'] = ProblemSample.objects.filter(
            created_at__lt=old_ticket_before(age_months)
        ).count()
        # Match Dispose Containers -> Ready to Dispose: the container must be
        # non-empty, not already disposed, and every attached ticket must be
        # To be Disposed or Disposed.
        ready_workflows = [PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_DISPOSED]
        counts['containers_ready_to_dispose'] = (
            ProblemContainer.objects.filter(disposed_at__isnull=True)
            .annotate(
                dashboard_sample_count=Count('problem_samples'),
                dashboard_blocking_count=Count(
                    'problem_samples',
                    filter=~Q(problem_samples__current_workflow__in=ready_workflows),
                ),
            )
            .filter(dashboard_sample_count__gt=0, dashboard_blocking_count=0)
            .count()
        )

        # A tracking link is persisted only when the customer tracking email is
        # explicitly confirmed as sent. Count links created during the current
        # local calendar day (not a rolling 24-hour window).
        local_today = timezone.localdate(now)
        tz = timezone.get_current_timezone()
        today_start = timezone.make_aware(datetime.combine(local_today, time.min), tz)
        tomorrow_start = timezone.make_aware(
            datetime.combine(local_today + timedelta(days=1), time.min), tz
        )
        counts['tracking_emails_today'] = ProblemTrackingLink.objects.filter(
            date_created__gte=today_start,
            date_created__lt=tomorrow_start,
        ).count()
        counts['customer_responded'] = _customer_responded_tickets().count()
        counts['custom'] = None
        custom_payload = None
        if custom:
            start_date, end_date, custom_start, custom_end = custom
            counts['custom'] = opened_tickets.filter(
                created_at__gte=custom_start, created_at__lt=custom_end
            ).count()
            custom_payload = {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()}

        if selected == 'custom':
            if not custom:
                return Response({'detail': 'Choose custom dates before using the Custom graph.'}, status=400)
            start_date, end_date, chart_start, chart_end = custom
            span_days = (end_date - start_date).days + 1
            bucket = 'day' if span_days <= 62 else 'week' if span_days <= 240 else 'month'
            range_label = f'{start_date.isoformat()} to {end_date.isoformat()}'
        else:
            chart_start = now - WINDOWS[selected]
            chart_end = now
            bucket = 'day' if selected in {'week', 'month'} else 'week' if selected == 'six_months' else 'month'
            range_label = {
                'week': 'Last 7 days',
                'month': 'Last 30 days',
                'six_months': 'Last 6 months',
                'year': 'Last year',
            }[selected]

        points = _series(opened_tickets, 'created_at', chart_start, chart_end, bucket)
        automatic_disposal_points = _series(
            AutomaticDisposalExpiryEvent.objects.all(),
            'effective_at',
            chart_start,
            chart_end,
            bucket,
        )
        return Response({
            'generated_at': now.isoformat(),
            'selected_table': ({'id': str(selected_table.id), 'name': selected_table.name} if selected_table else None),
            'counts': counts,
            'old_ticket_definition': {
                'age_months': age_months,
                'created_before': old_ticket_anniversary(age_months).isoformat(),
            },
            'custom': custom_payload,
            'chart': {
                'range': selected,
                'range_label': range_label,
                'bucket': bucket,
                'total': sum(point['count'] for point in points),
                'points': points,
            },
            'automatic_disposal_chart': {
                'range': selected,
                'range_label': range_label,
                'bucket': bucket,
                'total': sum(point['count'] for point in automatic_disposal_points),
                'points': automatic_disposal_points,
            },
        })



class DashboardStorageView(APIView):
    """Actual image/media storage telemetry for the staff dashboard."""

    def get(self, request):
        return Response(image_storage_stats())


class DashboardOpenedTicketsView(APIView):
    """Cross-table ticket list matching one of the dashboard opened-date cards."""

    PAGE_SIZE = 50

    def get(self, request):
        selected = str(request.query_params.get('range') or '').strip().lower()
        valid_ranges = set(WINDOWS) | {'custom'}
        if selected not in valid_ranges:
            return Response({'detail': 'Invalid opened-ticket range.'}, status=400)

        now = timezone.now()
        if selected == 'custom':
            try:
                start_date, end_date, start_at, end_at = _custom_bounds(
                    request.query_params.get('start_date'),
                    request.query_params.get('end_date'),
                )
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=400)
            tickets = ProblemSample.objects.filter(created_at__gte=start_at, created_at__lt=end_at)
            range_label = f'{start_date.isoformat()} to {end_date.isoformat()}'
        else:
            tickets = ProblemSample.objects.filter(created_at__gte=now - WINDOWS[selected])
            range_label = {
                'day': 'Last 24 hours',
                'week': 'Last 7 days',
                'month': 'Last 30 days',
                'six_months': 'Last 6 months',
                'year': 'Last year',
            }[selected]

        try:
            page = int(request.query_params.get('page') or 1)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid page.'}, status=400)
        if page < 1:
            return Response({'detail': 'Invalid page.'}, status=400)

        tickets = tickets.select_related('table').order_by('-created_at', '-pk')
        count = tickets.count()
        start = (page - 1) * self.PAGE_SIZE
        rows = list(tickets[start:start + self.PAGE_SIZE])
        return Response({
            'count': count,
            'page': page,
            'page_size': self.PAGE_SIZE,
            'range': selected,
            'range_label': range_label,
            'results': [{
                'id': str(ticket.pk),
                'problem_number': ticket.problem_number,
                'table_id': str(ticket.table_id) if ticket.table_id else '',
                'table_name': ticket.table.name if ticket.table else '—',
                'current_workflow': ticket.workflow_status,
                'created_at': ticket.created_at,
            } for ticket in rows],
        })


class CustomerRespondedTicketsView(APIView):
    """Tickets whose latest human history entry is Customer and workflow is eligible."""

    def get(self, request):
        from uuid import UUID

        table_id = str(request.query_params.get('table') or '').strip()
        if table_id:
            try:
                UUID(table_id)
            except ValueError:
                return Response({'detail': 'Invalid table ID.'}, status=400)
        try:
            page = int(request.query_params.get('page') or 1)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid page.'}, status=400)
        if page < 1:
            return Response({'detail': 'Invalid page.'}, status=400)

        tickets = _customer_responded_tickets().select_related('table')
        if table_id:
            tickets = tickets.filter(table_id=table_id)
        query = str(request.query_params.get('q') or '').strip()[:100]
        if query:
            match = Q(table__name__icontains=query) | Q(current_workflow__icontains=query)
            if query.lstrip('#').isdigit():
                match |= Q(problem_number=int(query.lstrip('#')))
            tickets = tickets.filter(match)
        count = tickets.count()
        rows = list(tickets.order_by('-last_response_at', '-created_at', '-pk')[(page-1)*50:page*50])
        # Load the latest response details for only the tickets on this page.
        latest = {}
        if rows:
            for history in ProblemHistory.objects.filter(
                problem_id__in=[row.pk for row in rows]
            ).filter(CUSTOMER_HISTORY).filter(
                Q(details__automatic__isnull=True) | Q(details__automatic=False)
            ).order_by('-created_at', '-id').values('problem_id', 'details'):
                latest.setdefault(history['problem_id'], history['details'])
        return Response({
            'count': count,
            'page': page,
            'page_size': 50,
            'results': [{
                'id': str(row.pk),
                'problem_number': row.problem_number,
                'table_name': row.table.name if row.table else '—',
                'current_workflow': row.workflow_status,
                'created_at': row.created_at,
                'responded_at': row.last_response_at,
                'customer_response': (latest.get(row.pk) or {}).get('customer_action_label') or 'Acknowledged',
            } for row in rows],
        })
