"""Review/confirm API for prepared system mail, using the normal external mail app."""
import uuid
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import ProblemColumn, SystemEmail
from accounts.models import Lab
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
    """Prepare month-to-date drafts for chosen labs; never send email automatically."""
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
            pk=request.data.get('column_id'), column_type=ProblemColumn.TYPE_BRAND,
        )
        rule = next((r for r in (column.brand_cc_rules or []) if isinstance(r, dict) and r.get('id') == str(rule_id)), None)
        if not rule or rule.get('pending_brand_review') or rule.get('send_monthly_reports') is not True or not rule.get('pattern') or not normalize_addresses(rule.get('cc_emails')):
            return Response({'detail': 'Save an enabled monthly report rule with a pattern and recipients first.'}, status=400)
        # Lab: All requires an explicit, validated selection. A single-lab view
        # keeps the existing one-email behavior for backward compatibility.
        selected_lab = active_lab(request)
        lab_ids = request.data.get('lab_ids')
        all_labs = request.data.get('all_labs', False)
        if selected_lab is None:
            if not isinstance(all_labs, bool):
                return Response({'detail': 'all_labs must be true or false.'}, status=400)
            if all_labs:
                if lab_ids is not None:
                    return Response({'detail': 'Choose either all_labs or lab_ids, not both.'}, status=400)
                labs = list(Lab.objects.order_by('name', 'id'))
            else:
                if (not isinstance(lab_ids, list) or not lab_ids or
                        len(lab_ids) > 200 or
                        any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in lab_ids) or
                        len(set(lab_ids)) != len(lab_ids)):
                    return Response({'detail': 'Select one or more valid labs, or choose All Labs.'}, status=400)
                available = {lab.pk: lab for lab in Lab.objects.filter(pk__in=lab_ids)}
                if len(available) != len(lab_ids):
                    return Response({'detail': 'One or more selected labs do not exist.'}, status=400)
                labs = [available[lab_id] for lab_id in lab_ids]
            if not labs:
                return Response({'detail': 'No labs are available for reporting.'}, status=400)
        else:
            if lab_ids is not None or all_labs is not False:
                return Response({'detail': 'Switch to Lab: All to select multiple labs.'}, status=400)
            labs = [selected_lab]

        reports = []
        # A retry of the same request produces the same per-lab identifiers,
        # without duplicating pending reports. Atomic across the entire batch.
        try:
            with transaction.atomic():
                for lab in labs:
                    identifier = (request_id if len(labs) == 1 and selected_lab is not None
                                  else uuid.uuid5(request_id, f'monthly-brand-report-lab:{lab.pk}'))
                    mail, created = queue_manual_monthly_report(
                        column, rule, request_identifier=identifier, lab=lab,
                    )
                    reports.append({'email_id': str(mail.id), 'lab_id': lab.pk,
                                    'lab_name': lab.name, 'created': created, 'status': mail.status})
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=409)
        count = sum(int(report['created']) for report in reports)
        return Response({'email_id': reports[0]['email_id'], 'email_ids': [r['email_id'] for r in reports],
                         'reports': reports, 'created': count > 0, 'created_count': count,
                         'status': reports[0]['status']},
                        status=status.HTTP_201_CREATED if count else status.HTTP_200_OK)
