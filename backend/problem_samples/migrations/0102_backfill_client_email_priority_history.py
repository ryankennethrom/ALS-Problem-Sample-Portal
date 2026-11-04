"""Initialize legacy Client Email escalation timers from actual ticket activity.

Only confirmed tracking-link sends qualify.  Ordinary customer emails, failed
send attempts and ticket creation times must not start an escalation window.
"""
from django.db import migrations
from django.db.models import Q


TRACKING_SENT_SUMMARY = 'Sent tracking link to customer by email'
CUSTOMER_RESPONSE_SOURCES = ('public_tracking_link', 'public_acknowledgement_link')


def _latest_history_dates(rows):
    """Return the latest event date for each ticket from sorted history rows.

    ``rows`` is ordered by ticket, then descending date and ID; this utility is
    intentionally independent of the ORM so the backfill can be unit-tested.
    """
    latest = {}
    for ticket_id, created_at in rows:
        if ticket_id not in latest and created_at is not None:
            latest[ticket_id] = created_at
    return latest


def _backfilled_dates(existing_sent, existing_response, acknowledged_at,
                      historical_sent, historical_response):
    """Preserve live timers; fill missing ones using recorded history.

    Acknowledgement timestamps count as customer activity, even if an older
    version did not create a separate customer-response history record.
    """
    sent = existing_sent if existing_sent is not None else historical_sent
    if existing_response is not None:
        response = existing_response
    else:
        known_responses = [item for item in (acknowledged_at, historical_response) if item is not None]
        response = max(known_responses) if known_responses else None
    return sent, response


def backfill_from_history(apps, schema_editor):
    Ticket = apps.get_model('problem_samples', 'ProblemSample')
    History = apps.get_model('problem_samples', 'ProblemHistory')
    alias = schema_editor.connection.alias

    sends = History.objects.using(alias).filter(
        summary=TRACKING_SENT_SUMMARY,
        action='customer_notification',
    ).order_by('problem_id', '-created_at', '-pk').values_list(
        'problem_id', 'created_at',
    ).iterator(chunk_size=2000)
    sent_at = _latest_history_dates(sends)

    responses = History.objects.using(alias).filter(
        Q(action='acknowledged') | Q(details__responded_via__in=CUSTOMER_RESPONSE_SOURCES)
    ).order_by('problem_id', '-created_at', '-pk').values_list(
        'problem_id', 'created_at',
    ).iterator(chunk_size=2000)
    response_at = _latest_history_dates(responses)

    pending = []
    for ticket in Ticket.objects.using(alias).filter(
        Q(client_email_last_tracking_sent_at__isnull=True) |
        Q(client_email_last_customer_response_at__isnull=True)
    ).only('pk', 'client_email_last_tracking_sent_at',
           'client_email_last_customer_response_at', 'acknowledged_at').iterator(chunk_size=1000):
        sent, response = _backfilled_dates(
            ticket.client_email_last_tracking_sent_at,
            ticket.client_email_last_customer_response_at,
            ticket.acknowledged_at,
            sent_at.get(ticket.pk), response_at.get(ticket.pk),
        )
        if (sent == ticket.client_email_last_tracking_sent_at and
                response == ticket.client_email_last_customer_response_at):
            continue
        ticket.client_email_last_tracking_sent_at = sent
        ticket.client_email_last_customer_response_at = response
        pending.append(ticket)
        if len(pending) >= 500:
            Ticket.objects.using(alias).bulk_update(
                pending,
                ['client_email_last_tracking_sent_at', 'client_email_last_customer_response_at'],
                batch_size=500,
            )
            pending.clear()
    if pending:
        Ticket.objects.using(alias).bulk_update(
            pending,
            ['client_email_last_tracking_sent_at', 'client_email_last_customer_response_at'],
            batch_size=500,
        )


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0101_client_email_priority_escalation')]
    operations = [migrations.RunPython(backfill_from_history, migrations.RunPython.noop)]
