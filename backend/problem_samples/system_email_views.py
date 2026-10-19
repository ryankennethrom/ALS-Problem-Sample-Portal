"""Review/confirm API for prepared system mail, using the normal external mail app."""
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import SystemEmail
from .system_email_service import queue_due_monthly_reports


def serialize_mail(message, detail=False):
    item = {
        'id': str(message.id), 'type': message.email_type, 'status': message.status,
        'table': message.source_column.table.name,
        'distributor_pattern': message.distributor_pattern,
        'period_start': message.period_start.isoformat(),
        'period_end': message.period_end.isoformat(),
        'matched_ticket_count': message.matched_ticket_count,
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
        queryset = SystemEmail.objects.select_related('source_column__table')
        if request.query_params.get('status') != 'all':
            queryset = queryset.filter(status=SystemEmail.STATUS_PENDING)
        if request.query_params.get('summary') == '1':
            return Response({'pending_count': SystemEmail.objects.filter(status=SystemEmail.STATUS_PENDING).count()})
        return Response({'pending_count': SystemEmail.objects.filter(status=SystemEmail.STATUS_PENDING).count(),
                         'emails': [serialize_mail(mail) for mail in queryset[:200]]})


class SystemEmailDetailView(APIView):
    def get(self, request, email_id):
        mail = get_object_or_404(SystemEmail.objects.select_related('source_column__table'), pk=email_id)
        return Response(serialize_mail(mail, detail=True))


class ConfirmSystemEmailView(APIView):
    def post(self, request, email_id):
        if request.data.get('confirmation') != 'sent':
            return Response({'detail': 'Confirm that you actually sent the message in your email application.'}, status=400)
        with transaction.atomic():
            mail = get_object_or_404(SystemEmail.objects.select_for_update(), pk=email_id)
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
        profile = getattr(request.user, 'tracker_profile', None)
        if not (request.user.is_superuser or request.user.is_staff or (profile and profile.is_admin)):
            return Response({'detail': 'Administrator access is required to queue due reports manually.'}, status=403)
        return Response(queue_due_monthly_reports())
