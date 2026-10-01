"""Administrator-only preview and deletion of finished, old tickets."""

import hashlib
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views import is_tracker_admin
from .models import (
    OldTicketDefinition,
    ProblemSample,
    PROBLEM_STATUS_BACK_TO_TESTING,
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_SHIPPED_BACK,
)
from .old_tickets import old_ticket_age_months, old_ticket_end_date


FINISHED_WORKFLOWS = (
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_SHIPPED_BACK,
    PROBLEM_STATUS_BACK_TO_TESTING,
)


def _default_end_date():
    return old_ticket_end_date()


class OldTicketDefinitionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_tracker_admin(request.user):
            return Response({'detail': 'Administrator access required.'}, status=403)
        months = old_ticket_age_months()
        return Response({'age_months': months, 'default_end_date': old_ticket_end_date(months).isoformat()})

    def put(self, request):
        if not is_tracker_admin(request.user):
            return Response({'detail': 'Administrator access required.'}, status=403)
        months = request.data.get('age_months')
        if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= 1200:
            return Response({'detail': 'Age must be a whole number of months from 1 to 1200.'}, status=400)
        with transaction.atomic():
            definition, _ = OldTicketDefinition.objects.update_or_create(
                pk=1, defaults={'age_months': months, 'updated_by': request.user},
            )
        return Response({'age_months': definition.age_months, 'default_end_date': old_ticket_end_date(months).isoformat()})


def _bounds(start_text, end_text):
    if not end_text:
        raise ValueError('Choose an end date.')
    end = parse_date(str(end_text))
    start = parse_date(str(start_text)) if start_text else None
    if not end or (start_text and not start):
        raise ValueError('Dates must use YYYY-MM-DD.')
    if end > timezone.localdate():
        raise ValueError('The end date cannot be in the future.')
    if start and start > end:
        raise ValueError('The start date cannot be after the end date.')
    tz = timezone.get_current_timezone()
    start_at = timezone.make_aware(datetime.combine(start, time.min), tz) if start else None
    end_at = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
    return start, end, start_at, end_at


def _candidates(start_at, end_at):
    queryset = ProblemSample.objects.filter(
        current_workflow__in=FINISHED_WORKFLOWS,
        created_at__lt=end_at,
    )
    return queryset.filter(created_at__gte=start_at) if start_at else queryset


def _snapshot(queryset):
    """The preview must match the exact set that is subsequently deleted."""
    fingerprint = hashlib.sha256()
    ids = []
    for pk in queryset.order_by('pk').values_list('pk', flat=True).iterator():
        fingerprint.update(pk.bytes)
        ids.append(pk)
    return len(ids), fingerprint.hexdigest(), ids


class TerminalTicketCleanupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_tracker_admin(request.user):
            return Response({'detail': 'Administrator access required.'}, status=403)
        start_text = request.query_params.get('start_date') or ''
        end_text = request.query_params.get('end_date') or _default_end_date().isoformat()
        try:
            start, end, start_at, end_at = _bounds(start_text, end_text)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        queryset = _candidates(start_at, end_at)
        count, fingerprint, _ = _snapshot(queryset)
        by_workflow = {
            workflow: queryset.filter(current_workflow=workflow).count()
            for workflow in FINISHED_WORKFLOWS
        }
        return Response({
            'start_date': start.isoformat() if start else '',
            'end_date': end.isoformat(),
            'count': count,
            'by_workflow': by_workflow,
            'fingerprint': fingerprint,
        })

    def post(self, request):
        if not is_tracker_admin(request.user):
            return Response({'detail': 'Administrator access required.'}, status=403)
        start_text = request.data.get('start_date') or ''
        end_text = request.data.get('end_date')
        try:
            start, end, start_at, end_at = _bounds(start_text, end_text)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        expected_count = request.data.get('expected_count')
        expected_fingerprint = request.data.get('fingerprint')
        if not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count < 1:
            return Response({'detail': 'Preview at least one ticket before deleting.'}, status=400)
        if not isinstance(expected_fingerprint, str) or len(expected_fingerprint) != 64:
            return Response({'detail': 'Preview the tickets again before deleting.'}, status=400)
        if request.data.get('confirmation') != f'DELETE {expected_count}':
            return Response({'detail': f'Type DELETE {expected_count} to confirm.'}, status=400)

        with transaction.atomic():
            queryset = _candidates(start_at, end_at).select_for_update()
            count, fingerprint, ids = _snapshot(queryset)
            if count != expected_count or fingerprint != expected_fingerprint:
                return Response({'detail': 'The matching tickets changed. Preview again before deleting.'}, status=409)
            ProblemSample.objects.filter(pk__in=ids).delete()

        return Response({'deleted_tickets': count, 'start_date': start.isoformat() if start else '', 'end_date': end.isoformat()})
