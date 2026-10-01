from django.db import migrations


class Migration(migrations.Migration):
    """Replace a stale, incorrectly generated migration.

    The previous local version attempted to remove ``ProblemSample.customer_action``,
    but that has never been a model field in this migration state. Customer action
    data is stored in ``customer_acknowledgement_action``; ``customer_action`` is
    only used as a key in history/API JSON.

    Migration 0067 already brings the real model field to the desired state, so
    this graph node intentionally performs no database or state operations.
    """

    dependencies = [
        ('problem_samples', '0067_customer_requested_information_label'),
    ]

    operations = []
