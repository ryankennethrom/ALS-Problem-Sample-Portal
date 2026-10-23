"""Server-authoritative timing capture and admin-only elapsed-time reports."""
from datetime import datetime, time, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TicketCreationTiming
from .labs import active_lab


def _admin(user):
    profile = getattr(user, 'tracker_profile', None)
    return bool(user.is_superuser or (profile and profile.is_admin))


def _display_name(user):
    return (user.get_full_name() or user.email or user.username).strip()


class StartTicketCreationTimingView(APIView):
    def post(self, request):
        # Abandoned attempts are not reported. Bound their storage usage as they
        # have no ticket and no business/audit value after two weeks.
        TicketCreationTiming.objects.filter(
            completed_at__isnull=True, started_at__lt=timezone.now() - timedelta(days=14),
        ).delete()
        record = TicketCreationTiming.objects.create(
            lab=active_lab(request, require_specific=True), staff=request.user, staff_label=_display_name(request.user),
        )
        return Response({'id': str(record.id), 'started_at': record.started_at.isoformat()},
                        status=status.HTTP_201_CREATED)


class TicketCreationTimeReportView(APIView):
    """Completed successful creations, grouped by local completion day and user."""
    def get(self, request):
        if not _admin(request.user):
            return Response({'detail': 'Administrator access required.'}, status=403)
        today = timezone.localdate()
        start = parse_date(request.query_params.get('start_date', '')) if request.query_params.get('start_date') else today - timedelta(days=6)
        end = parse_date(request.query_params.get('end_date', '')) if request.query_params.get('end_date') else today
        if not start or not end or end < start or (end - start).days > 366:
            return Response({'detail': 'Enter a valid date range of at most 367 days.'}, status=400)
        tz = timezone.get_current_timezone()
        begin = timezone.make_aware(datetime.combine(start, time.min), tz)
        finish = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
        lab = active_lab(request)
        source = TicketCreationTiming.objects.filter(lab=lab) if lab else TicketCreationTiming.objects.all()
        summaries = (source.filter(
            completed_at__gte=begin, completed_at__lt=finish,
            duration_ms__isnull=False,
        ).annotate(day=TruncDate('completed_at', tzinfo=tz))
            .values('day', 'staff_id', 'staff_label')
            .annotate(tickets=Count('id'), duration_ms=Sum('duration_ms'))
            .order_by('day', 'staff_label'))
        by_staff = {}
        by_day = {}
        for row in summaries:
            key = (row['staff_id'], row['staff_label'])
            total_ms = int(row['duration_ms'] or 0)
            count = int(row['tickets'])
            if key not in by_staff:
                by_staff[key] = {'staff_id': row['staff_id'], 'staff_name': row['staff_label'],
                                 'tickets': 0, 'total_ms': 0}
            by_staff[key]['tickets'] += count
            by_staff[key]['total_ms'] += total_ms
            day = row['day'].isoformat()
            if day not in by_day:
                by_day[day] = {'date': day, 'tickets': 0, 'total_ms': 0, 'staff': []}
            by_day[day]['tickets'] += count
            by_day[day]['total_ms'] += total_ms
            by_day[day]['staff'].append({
                'staff_id': row['staff_id'], 'staff_name': row['staff_label'],
                'tickets': count, 'total_ms': total_ms,
                'average_ms': round(total_ms / count),
            })
        staff = sorted(by_staff.values(), key=lambda row: (row['staff_name'].lower(), row['staff_id'] or 0))
        for row in staff:
            row['average_ms'] = round(row['total_ms'] / row['tickets'])
        daily = [by_day[day] for day in sorted(by_day, reverse=True)]
        ticket_count = sum(day['tickets'] for day in daily)
        total_ms = sum(day['total_ms'] for day in daily)
        return Response({
            'start_date': start.isoformat(), 'end_date': end.isoformat(), 'today': today.isoformat(),
            'timezone': str(tz),
            'summary': {'tickets': ticket_count, 'total_ms': total_ms,
                        'average_ms': round(total_ms / ticket_count) if ticket_count else 0},
            'staff': staff, 'daily': daily,
        })
