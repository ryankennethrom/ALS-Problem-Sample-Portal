"""Review/confirm API for prepared system mail, using the normal external mail app."""
import uuid
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import ProblemColumn, SystemEmail
from .labs import active_lab
from .system_email_service import queue_due_monthly_reports, queue_manual_monthly_report, normalize_addresses


def is_admin(user):
    profile = getattr(user, 'tracker_profile', None)
    return user.is_superuser or user.is_staff or (profile and profile.is_admin)


def serialize_mail(message, detail=False):
    item = {
        'id': str(message.id), 'type': message.email_type, 'status': message.status,
        'table': message.source_column.table.name,
        'distributor_pattern': message.distributor_pattern,
        'period_start': message.period_start.isoformat(),
        'period_end': message.period_end.isoformat(),
        'matched_ticket_count': message.matched_ticket_count,
        'generation_mode': message.generation_mode,
        'recipient_count': len(message.to_emails),
        'subject': message.subject,
        'created_at': message.created_at.isoformat(),
        'sent_at': message.sent_at.isoformat() if message.sent_at else None,
    }
    if detail:
        item['to_emails'] = message.to_emails
        item['body'] = message.body
    return item


class SystemEmailListView(APIView):
    def get(self, request):
        lab = active_lab(request)
        queryset = SystemEmail.objects.select_related('source_column__table')
        if lab: queryset = queryset.filter(lab=lab)
        if request.query_params.get('status') != 'all':
            queryset = queryset.filter(status=SystemEmail.STATUS_PENDING)
        if request.query_params.get('summary') == '1':
            return Response({'pending_count': queryset.filter(status=SystemEmail.STATUS_PENDING).count()})
        return Response({'pending_count': queryset.filter(status=SystemEmail.STATUS_PENDING).count(),
                         'emails': [serialize_mail(mail) for mail in queryset[:200]]})


class SystemEmailDetailView(APIView):
    def get(self, request, email_id):
        lab = active_lab(request)
        qs = SystemEmail.objects.select_related('source_column__table')
        mail = get_object_or_404(qs.filter(lab=lab) if lab else qs, pk=email_id)
        return Response(serialize_mail(mail, detail=True))


class ConfirmSystemEmailView(APIView):
    def post(self, request, email_id):
        if request.data.get('confirmation') != 'sent':
            return Response({'detail': 'Confirm that you actually sent the message in your email application.'}, status=400)
        with transaction.atomic():
            lab = active_lab(request)
            qs = SystemEmail.objects.select_for_update()
            mail = get_object_or_404(qs.filter(lab=lab) if lab else qs, pk=email_id)
            if mail.status != SystemEmail.STATUS_PENDING:
                return Response({'detail': 'This system email has already been marked sent.'}, status=status.HTTP_409_CONFLICT)
            mail.status = SystemEmail.STATUS_SENT
            mail.sent_by = request.user
            mail.sent_at = timezone.now()
            mail.save(update_fields=['status', 'sent_by', 'sent_at'])
        return Response({'status': mail.status, 'sent_at': mail.sent_at.isoformat()})


class QueueDueSystemEmailsView(APIView):
    def post(self, request):
        # Manual catch-up is admin-only; scheduled Django management command runs as a service.
        if not is_admin(request.user):
            return Response({'detail': 'Administrator access is required to queue due reports manually.'}, status=403)
        return Response(queue_due_monthly_reports())


class QueueManualDistributorReportView(APIView):
    """Create one month-to-date draft and return its ID for the review/send page."""
    def post(self, request):
        if not is_admin(request.user):
            return Response({'detail': 'Administrator access is required to generate a report.'}, status=403)
        try:
            rule_id = uuid.UUID(str(request.data.get('rule_id', '')))
            request_id = uuid.UUID(str(request.data.get('request_id', '')))
        except (ValueError, AttributeError, TypeError):
            return Response({'detail': 'A valid rule_id and request_id are required.'}, status=400)
        column = get_object_or_404(
            ProblemColumn.objects.select_related('table'),
            pk=request.data.get('column_id'), column_type=ProblemColumn.TYPE_DISTRIBUTOR,
        )
        rule = next((r for r in (column.distributor_cc_rules or []) if isinstance(r, dict) and r.get('id') == str(rule_id)), None)
        if not rule or rule.get('send_monthly_reports') is not True or not rule.get('pattern') or not normalize_addresses(rule.get('cc_emails')):
            return Response({'detail': 'Save an enabled monthly report rule with a pattern and recipients first.'}, status=400)
        try:
            mail, created = queue_manual_monthly_report(column, rule, request_identifier=request_id, lab=active_lab(request, require_specific=True))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=409)
        return Response({'email_id': str(mail.id), 'created': created, 'status': mail.status},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
