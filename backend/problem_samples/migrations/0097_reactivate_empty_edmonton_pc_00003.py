"""Make the existing empty, legacy-disposed EDM PC-00003 reusable.

Reopen the SAME container row rather than reassigning PC-00003 to a new PK.
Leave tickets, source/destination FKs, and other container IDs unchanged.
Skip if the record is missing, already available, or has assigned tickets.
The prior disposal stamp is archived in the JSON snapshot for audit.
"""
from django.db import migrations
from django.utils import timezone


def reactivate_edmonton_pc_00003(apps, schema_editor):
    Container = apps.get_model('problem_samples', 'ProblemContainer')
    db = schema_editor.connection.alias
    container = (Container.objects.using(db).filter(
        lab__code__iexact='EDM', lab_number=3, is_dumping=False,
        disposed_at__isnull=False,
    ).first())
    if container is None or container.problem_samples.using(db).exists():
        return

    # Archive the original legacy disposal timestamp and actor, without
    # affecting existing disposal snapshots or rewriting historical tickets.
    snapshot = dict(container.disposal_snapshot or {})
    events = list(snapshot.get('_legacy_reactivation_events') or [])
    events.append({
        'disposed_at': container.disposed_at.isoformat(),
        'disposed_by_id': container.disposed_by_id,
        'reactivated_at': timezone.now().isoformat(),
        'reactivated_by_id': None,
        'reason': 'Made existing empty EDM PC-00003 available by migration 0097',
    })
    snapshot['_legacy_reactivation_events'] = events
    container.disposal_snapshot = snapshot
    container.disposed_at = None
    container.disposed_by_id = None
    container.save(using=db, update_fields=['disposal_snapshot', 'disposed_at', 'disposed_by'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0096_separate_dumping_container_numbers'),
    ]
    # Not safely reversible if the original physical PC has been put back in use.
    operations = [migrations.RunPython(reactivate_edmonton_pc_00003, migrations.RunPython.noop)]
