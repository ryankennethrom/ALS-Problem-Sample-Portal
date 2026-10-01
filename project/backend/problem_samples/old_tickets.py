"""One calendar-month definition shared by the dashboard and cleanup defaults."""

from calendar import monthrange
from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import OldTicketDefinition


DEFAULT_AGE_MONTHS = 24


def old_ticket_age_months():
    return (OldTicketDefinition.objects.filter(pk=1).values_list('age_months', flat=True).first()
            or DEFAULT_AGE_MONTHS)


def old_ticket_anniversary(age_months=None, today=None):
    age_months = age_months if age_months is not None else old_ticket_age_months()
    today = today or timezone.localdate()
    month_index = today.year * 12 + today.month - 1 - age_months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return today.replace(year=year, month=month, day=min(today.day, monthrange(year, month)[1]))


def old_ticket_end_date(age_months=None, today=None):
    # End dates are inclusive, so use the preceding day to exclude tickets
    # created later on the anniversary that are still less than N months old.
    return old_ticket_anniversary(age_months, today) - timedelta(days=1)


def old_ticket_before(age_months=None, today=None):
    """Old tickets have created_at strictly before this local midnight."""
    day = old_ticket_anniversary(age_months, today)
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())
