"""Immutable Brand monthly report snapshots, delivered as private Excel downloads.

Links are bearer credentials, valid for 90 days unless revoked. Never include
customer tracking tokens, credentials or attachment URLs in exported data.
"""
import io
import json
import re
import uuid
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SystemEmail

REPORT_LIFETIME_DAYS = 90


def report_url(mail):
    return f"{str(settings.FRONTEND_URL).rstrip('/')}/reports/monthly/{mail.public_token}"


def make_report_email_body(mail):
    """A short notification, never include the detailed report in the mailto body."""
    url = report_url(mail)
    return '\n'.join([
        'Hello,', '',
        f'Your {"month-to-date" if mail.generation_mode == "manual" else "monthly"} ALS Brand report is ready.',
        f'Lab: {mail.lab.name if mail.lab else "Unassigned"}',
        f'Report period: {mail.period_start.isoformat()} to {(mail.period_end - timedelta(days=1)).isoformat()}',
        f'Matching tickets: {mail.matched_ticket_count}', '',
        f'Download Excel monthly report: {url}', '',
        'IMPORTANT: The Excel workbook contains two worksheet tabs: Summary and Tickets.',
        'To view the ticket rows, open the Tickets tab at the bottom of Excel.',
        'The Summary tab shows report totals only.', '',
        f'This confidential link expires 90 days after report generation ({timezone.localtime(mail.public_expires_at).date().isoformat() if mail.public_expires_at else "not set"}).',
        'Do not forward the link outside its intended recipients.', '',
        'Prepared by ALS Ticket Tracker. Sending requires staff confirmation.',
    ])


def _safe_text(value, max_length=1000):
    if value is None: return ''
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    result = str(value)[:max_length]
    # Never expose customer tracking-link bearer URLs in third-party reports,
    # even if staff previously pasted one into a custom field or history summary.
    result = re.sub(r'(?i)(?:https?://[^\s]+)?/(?:track|acknowledge)/[a-z0-9_-]+', '[tracking link redacted]', result)
    result = re.sub(r'(?i)(tracking[_ -]?token\s*[:=]\s*)[^\s,;]+', r'\1[redacted]', result)
    return result


# Never include direct tracking links, email addresses, login tokens, secrets or
# payment credentials in a bearer-link report, even if an admin selects them.
# Use the same predicate for serializer validation and snapshot generation.
def reportable_column(field):
    label = f"{getattr(field, 'name', '')} {getattr(field, 'field_key', '')}".lower()
    forbidden = ('tracking link', 'tracking-link', 'tracking_token', 'tracking-token',
                 'password', 'secret', 'api key', 'courier account', 'client email',
                 'contact email', 'email address', 'access token', 'access-token')
    return not any(phrase in label for phrase in forbidden) and getattr(field, 'column_type', '') != 'client_email'


def snapshot_tickets(column, rule, start, end, matches, lab):
    """Capture exact columns and values at generation time; never query mutable tickets at download."""
    from .brand_email_rules import brand_values_by_source, brand_matches

    table_columns = list(column.table.columns.all().order_by('position', 'created_at'))
    column_names = {str(field.pk): field.name for field in table_columns}
    eligible = [field for field in table_columns if reportable_column(field)]
    configured_ids = rule.get('report_column_ids')  # None = all eligible (legacy/default)
    if isinstance(configured_ids, list):
        enabled = set(configured_ids)
        eligible = [field for field in eligible if str(field.pk) in enabled]
    column_specs = [{'id': str(field.pk), 'label': _safe_text(field.name, 120)} for field in eligible]
    tickets = []
    company_cache = {}
    for ticket in matches:
        values = ticket.custom_values or {}
        sources = brand_values_by_source(column, values, company_cache=company_cache)
        matched_sources = [
            'Ticket Brand' if source == 'ticket' else column_names.get(source, 'Company Brand')
            for source, brands in sources.items()
            if source in rule.get('sources', ['ticket']) and any(brand_matches(value, rule) for value in brands)
        ]
        details = []
        for field in eligible:
            if field.field_key == 'current-workflow':
                value = ticket.current_workflow
            else:
                value = values.get(field.field_key)
                if value is None and field.field_key == 'brand':
                    value = ticket.brand
                if value is None and field.field_key == 'distributor':
                    value = ticket.distributor
                if value is None and field.field_key in ('end-user', 'end_user'):
                    value = ticket.end_user
            details.append({'id': str(field.pk), 'label': _safe_text(field.name, 120),
                            'value': _safe_text(value, 4000)})
        tickets.append({
            'number': ticket.problem_number,
            'status': _safe_text(ticket.current_workflow, 200),
            'created_at': ticket.created_at.isoformat(),
            'matched_sources': [_safe_text(s, 120) for s in matched_sources],
            'details': details,
        })
    return {
        'version': 2, 'format': 'xlsx', 'lab': lab.name if lab else 'Unassigned',
        'table': column.table.name,
        'rule_pattern': _safe_text(rule.get('pattern'), 160),
        'rule_match_type': _safe_text(rule.get('match_type'), 30),
        'period_start': start.isoformat(),
        'period_end': (end - timedelta(days=1)).isoformat(),
        'prepared_at': timezone.now().isoformat(),
        'columns': column_specs,
        'workflow_counts': dict(Counter(t['status'] for t in tickets)),
        'total': len(tickets), 'tickets': tickets,
    }


def finalize_report(mail):
    """Make a pending mail link-only. Must only run for newly created report jobs."""
    if not mail.report_snapshot or not mail.public_expires_at:
        return
    mail.body = make_report_email_body(mail)
    mail.save(update_fields=['body'])


def public_report_or_none(token):
    try:
        identifier = uuid.UUID(str(token))
    except (ValueError, TypeError, AttributeError):
        return None
    mail = SystemEmail.objects.filter(public_token=identifier).first()
    if not mail or not mail.report_snapshot or mail.public_revoked_at or not mail.public_expires_at or timezone.now() >= mail.public_expires_at:
        return None
    return mail


def private_headers(response):
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


class PublicMonthlyReportExcelView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        mail = public_report_or_none(token)
        if not mail:
            return private_headers(Response({'detail': 'Report not found or link expired.'}, status=404))
        response = HttpResponse(render_excel(mail.report_snapshot),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        lab_code = re.sub(r'[^A-Za-z0-9_-]', '', mail.lab.code if mail.lab else 'lab')[:30] or 'lab'
        response['Content-Disposition'] = f'attachment; filename="ALS-{mail.period_start.isoformat()}-{lab_code}-brand-report.xlsx"'
        return private_headers(response)


def _excel_value(value):
    """Keep untrusted values as inert text, never Excel formulas."""
    if value is None:
        return ''
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    value = _safe_text(value, 32000)
    if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    return value


def render_excel(snapshot):
    """Generate a polished two-tab Excel report from the immutable snapshot.

    Summary shows report metrics and explicitly points to the Tickets tab.
    Tickets contains wrapped, filterable ticket data and frozen identifiers.
    Stream ticket rows so large (20k+) reports remain manageable. Old saved
    snapshots are rendered in this same layout when downloaded again.
    """
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook(write_only=True)
    summary = wb.create_sheet('Summary')
    tickets_ws = wb.create_sheet('Tickets')
    for sheet in (summary, tickets_ws):
        sheet.sheet_view.showGridLines = False
    summary.freeze_panes = 'A3'
    tickets_ws.freeze_panes = 'C3'

    navy, teal = '142C46', '087F8C'
    slate, white = 'EAF1F6', 'FFFFFF'
    muted, ink = '63758A', '23364D'
    border_color = 'DCE5EE'

    def cell(ws, value='', kind='normal'):
        c = WriteOnlyCell(ws, value=_excel_value(value))
        styles = {
            'banner': (navy, white, True, 15),
            'banner_accent': (navy, '7DE2E5', True, 14),
            'subtitle': (slate, muted, False, 10),
            'label': (white, muted, True, 10),
            'metric': (white, ink, True, 12),
            'section': (teal, white, True, 11),
            'guide': ('FFF2D6', '865300', True, 10),
            'head': (navy, white, True, 10),
            'stripe': (white, ink, False, 10),
            'stripe_alt': ('F3F7FA', ink, False, 10),
            'status_active': ('FFF2D6', '865300', True, 10),
            'status_done': ('E1F5EA', '176E43', True, 10),
            'status_other': ('E3EEF9', '235783', True, 10),
        }
        fill, color, bold, size = styles[kind]
        c.font = Font(name='Aptos', size=size, color=color, bold=bold)
        c.fill = PatternFill('solid', fgColor=fill)
        c.alignment = Alignment(
            horizontal='left', vertical='top' if kind.startswith('stripe') else 'center',
            wrap_text=True, indent=1 if kind.startswith('stripe') else 0,
        )
        if kind.startswith('stripe') or kind.startswith('status_'):
            c.border = Border(bottom=Side(style='hair', color=border_color))
        return c

    # Prepare Summary tab: the report data is deliberately not on this tab.
    summary.column_dimensions['A'].width = 29
    summary.column_dimensions['B'].width = 44
    summary.column_dimensions['C'].width = 26
    summary.column_dimensions['D'].width = 42
    workflows = sorted(snapshot.get('workflow_counts', {}).items(),
                       key=lambda item: str(item[0]).casefold())
    for row, height in {1:40, 2:25, 3:37, 4:37, 5:37, 6:44, 7:31}.items():
        summary.row_dimensions[row].height = height
    for index in range(len(workflows)):
        summary.row_dimensions[8 + index].height = 30

    summary.append([cell(summary, 'ALS TICKET TRACKER', 'banner'),
                    cell(summary, 'MONTHLY BRAND REPORT', 'banner_accent'),
                    cell(summary, '', 'banner'), cell(summary, '', 'banner')])
    summary.append([cell(summary, 'CONFIDENTIAL • GENERATED REPORT', 'subtitle')])
    summary.append([
        cell(summary, 'MATCHING TICKETS', 'label'),
        cell(summary, snapshot.get('total', len(snapshot.get('tickets', []))), 'metric'),
        cell(summary, 'LAB', 'label'),
        cell(summary, snapshot.get('lab', ''), 'metric'),
    ])
    summary.append([
        cell(summary, 'REPORT PERIOD', 'label'),
        cell(summary, f"{snapshot.get('period_start', '')} to {snapshot.get('period_end', '')}", 'metric'),
        cell(summary, 'BRAND PATTERN', 'label'),
        cell(summary, snapshot.get('rule_pattern', ''), 'metric'),
    ])
    summary.append([
        cell(summary, 'GENERATED', 'label'),
        cell(summary, snapshot.get('prepared_at', ''), 'metric'),
        cell(summary, 'TICKET TABLE', 'label'),
        cell(summary, snapshot.get('table', ''), 'metric'),
    ])
    summary.append([
        cell(summary, 'WHERE ARE THE TICKETS?', 'guide'),
        cell(summary, 'Open the Tickets worksheet tab at the bottom of Excel to view every ticket row.', 'guide'),
        cell(summary, 'THIS TAB', 'guide'),
        cell(summary, 'Summary and workflow counts only', 'guide'),
    ])
    summary.append([cell(summary, 'CURRENT WORKFLOW', 'section'),
                    cell(summary, 'TICKET COUNT', 'section')])
    for status, count in workflows:
        summary.append([cell(summary, status, 'stripe'), cell(summary, count, 'metric')])

    # Prepare Tickets tab: header at row 2, first ticket at row 3.
    columns = snapshot.get('columns')
    if not isinstance(columns, list):
        labels = dict.fromkeys(d.get('label', '') for t in snapshot.get('tickets', [])
                               for d in t.get('details', []))
        columns = [{'id': label, 'label': label} for label in labels if label and reportable_column(
            type('LegacyColumn', (), {'name': label, 'field_key': label, 'column_type': ''})())]
    # 'Created' and 'Brand Matched Via' were old fixed report columns.
    # Omit them even from older saved snapshots so existing download links
    # receive the revised report layout too.
    columns = [c for c in columns if str(c.get('label', '')).strip().casefold()
               not in ('created', 'brand matched via')][:160]
    header = ['Ticket #', 'Current Workflow'] + [c.get('label', '') for c in columns]
    widths = [20, 29] + [34] * len(columns)
    for index, width in enumerate(widths, 1):
        tickets_ws.column_dimensions[get_column_letter(index)].width = width
    tickets_ws.row_dimensions[1].height = 38
    tickets_ws.row_dimensions[2].height = 43

    # WriteOnlyWorksheet serializes dimensions before row content. Heights must
    # therefore be determined before writing the data cells.
    max_records = 1048576 - 2
    for i, ticket in enumerate(snapshot.get('tickets', [])[:max_records], 3):
        selected = {str(d.get('id', d.get('label'))): d.get('value', '')
                    for d in ticket.get('details', [])}
        values = [ticket.get('number', ''), ticket.get('status', '')]
        values.extend(selected.get(str(c.get('id', c.get('label'))), '') for c in columns)
        max_lines = 1
        for value, width in zip(values, widths):
            chars_per_line = max(12, width - 4)
            for part in str(value if value is not None else '').splitlines() or ['']:
                max_lines = max(max_lines, (len(part) + chars_per_line - 1) // chars_per_line)
                if max_lines >= 10:
                    break
        tickets_ws.row_dimensions[i].height = min(150, max(27, 15 * min(max_lines, 10) + 8))

    tickets_ws.append([cell(tickets_ws, 'ALS TICKET TRACKER — MONTHLY BRAND REPORT', 'banner'),
                       cell(tickets_ws, 'TICKET DETAILS', 'banner_accent')])
    tickets_ws.append([cell(tickets_ws, value, 'head') for value in header])

    count = 0
    for ticket in snapshot.get('tickets', [])[:max_records]:
        selected = {str(d.get('id', d.get('label'))): d.get('value', '')
                    for d in ticket.get('details', [])}
        values = [ticket.get('number', ''), ticket.get('status', '')]
        values.extend(selected.get(str(c.get('id', c.get('label'))), '') for c in columns)
        style = 'stripe' if count % 2 == 0 else 'stripe_alt'
        row = [cell(tickets_ws, value, style) for value in values]
        if len(row) > 1:
            status = str(ticket.get('status', '')).casefold()
            kind = ('status_done' if any(s in status for s in ('disposed','back to testing','shipped back'))
                    else 'status_active' if any(s in status for s in ('follow','waiting','hold','required'))
                    else 'status_other')
            row[1] = cell(tickets_ws, values[1], kind)
        tickets_ws.append(row)
        count += 1
    tickets_ws.auto_filter.ref = f'A2:{get_column_letter(len(header))}{2 + count}'
    tickets_ws.sheet_properties.pageSetUpPr.fitToPage = True
    tickets_ws.print_title_rows = '2:2'

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
