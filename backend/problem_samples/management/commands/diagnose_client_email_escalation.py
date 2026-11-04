"""Read-only diagnostic for missing Client Email escalation history entries."""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from problem_samples.models import (
    ProblemSample, ProblemColumn, ProblemHistory,
    CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER,
)
from problem_samples.client_email_escalation import _emails_for_company, _infer_legacy_priority


class Command(BaseCommand):
    help = 'Explain why a ticket has not generated a Client Email escalation history entry (read only).'

    def add_arguments(self, parser):
        parser.add_argument('--ticket-number', type=int, help='Ticket number to inspect')
        parser.add_argument('--limit', type=int, default=30, help='Maximum tickets displayed without a number')

    def handle(self, *args, **options):
        qs = ProblemSample.objects.select_related('table').order_by('-created_at')
        if options['ticket_number'] is not None:
            qs = qs.filter(problem_number=options['ticket_number'])
        else:
            qs = qs.filter(current_workflow=CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER)[:max(1, options['limit'])]
        now = timezone.now()
        found = 0
        for ticket in qs:
            found += 1
            self.stdout.write(f'\nTicket #{ticket.problem_number} ({ticket.table.name if ticket.table else "No table"})')
            self.stdout.write(f'  Workflow: {ticket.workflow_status}')
            if ticket.current_workflow != ticket.workflow_status:
                self.stdout.write(self.style.WARNING(
                    f'  Workflow index differs: indexed={ticket.current_workflow!r}, '
                    f'custom field={ticket.workflow_status!r}; legacy JSON fallback is used.'
                ))
            self.stdout.write(f'  Last confirmed tracking send: {ticket.client_email_last_tracking_sent_at or "MISSING"}')
            self.stdout.write(f'  Last customer activity: {ticket.client_email_last_customer_response_at or "None"}')
            has_recorded_send = ProblemHistory.objects.filter(
                problem=ticket, action=ProblemHistory.ACTION_CUSTOMER_NOTIFICATION,
                summary='Sent tracking link to customer by email',
            ).exists()
            if not ticket.client_email_last_tracking_sent_at and has_recorded_send:
                self.stdout.write(self.style.WARNING('  Send history exists but timer is empty; run python manage.py migrate to apply 0103.'))
            if ticket.workflow_status != CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER:
                self.stdout.write('  NOT ELIGIBLE: workflow is not Waiting for Customer Response')
            if not ticket.table:
                self.stdout.write('  NOT ELIGIBLE: ticket has no table')
                continue
            columns = ticket.table.columns.filter(column_type=ProblemColumn.TYPE_CLIENT_EMAIL)
            if not columns.exists():
                self.stdout.write('  NOT ELIGIBLE: no Client Email column in ticket table')
            for column in columns:
                deps = column.ordered_client_email_dependency_columns()
                self.stdout.write(f'  Column {column.name}: timeout={column.client_email_fallback_hours!r} hours, dependencies={len(deps)}')
                if column.client_email_fallback_hours is None:
                    self.stdout.write('    BLOCKED: escalation setting disabled')
                    continue
                if len(deps) < 2:
                    self.stdout.write('    BLOCKED: fewer than two existing priority company columns')
                    continue
                known = (ticket.client_email_priority_state or {}).get(str(column.pk))
                inferred = False
                if type(known) is int and 0 <= known < len(deps):
                    position = known
                else:
                    position, inferred = _infer_legacy_priority(
                        deps, ticket.custom_values or {}, column.field_key,
                        emails_for_company=_emails_for_company,
                    )
                if position is None:
                    self.stdout.write('    BLOCKED: cannot infer historical priority; no saved Client Email addresses or no populated priority lists')
                    continue
                self.stdout.write(f'    Current priority: {position + 1} ({deps[position].name})' + (' [inferred from largest email overlap]' if inferred else (' [legacy tie / default]' if known is None else '')))
                if not ticket.client_email_last_tracking_sent_at:
                    self.stdout.write('    BLOCKED: missing confirmed tracking send timestamp')
                    continue
                last_response = ticket.client_email_last_customer_response_at
                anchor = max(ticket.client_email_last_tracking_sent_at, last_response) if last_response else ticket.client_email_last_tracking_sent_at
                deadline = anchor + timedelta(hours=column.client_email_fallback_hours)
                self.stdout.write(f'    Response deadline: {deadline}')
                if now < deadline:
                    self.stdout.write('    BLOCKED: response deadline has not passed')
                    continue
                if position >= len(deps) - 1:
                    self.stdout.write('    BLOCKED: already at final priority; no next list')
                    continue
                viable = []
                for next_position in range(position + 1, len(deps)):
                    dependency = deps[next_position]
                    company = str((ticket.custom_values or {}).get(dependency.field_key) or '').strip()
                    emails = _emails_for_company(company)
                    if emails:
                        viable.append(f'{next_position+1}: {dependency.name} ({len(emails)} email(s))')
                if not viable:
                    self.stdout.write('    BLOCKED: no populated later-priority company with email addresses in Customer Export')
                elif ticket.workflow_status == CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER:
                    self.stdout.write(self.style.SUCCESS('    ELIGIBLE: next contact ' + ', '.join(viable) + '; refresh app to run escalation check'))
        if not found:
            self.stdout.write(self.style.WARNING('No matching tickets found.'))
