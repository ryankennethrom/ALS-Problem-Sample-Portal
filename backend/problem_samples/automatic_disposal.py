from django.db import transaction
from django.utils import timezone

from .models import (
    ProblemSample,
)


def transition_due_automatic_disposals(*, now=None):
    """Persist all due automatic-disposal deadlines as workflow transitions.

    The exact deadline depends on each row's table.pt_days. This helper narrows
    candidates to rows that have ever started an automatic-disposal countdown,
    then lets the model apply the current Yes/No, due-time, and protected-status
    rules.
    It is safe to call repeatedly and from concurrent requests.
    """
    now = now or timezone.now()
    candidate_ids = list(
        ProblemSample.objects.filter(automatic_disposal_started_at__isnull=False)
        .values_list('pk', flat=True)
    )

    transitioned = 0
    for problem_id in candidate_ids:
        with transaction.atomic():
            problem = (
                ProblemSample.objects.select_for_update()
                .filter(pk=problem_id)
                .first()
            )
            if problem is not None and problem.transition_to_disposal_if_due(now=now):
                transitioned += 1
    return transitioned
