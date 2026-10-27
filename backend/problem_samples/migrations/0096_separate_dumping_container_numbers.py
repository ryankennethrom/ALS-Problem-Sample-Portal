"""Move dumping containers to independent per-lab DC numbering.

Keep every physical PC identifier stable. Existing DCs are numbered by
creation order within their lab; their ticket FKs and source/restore FKs are
unchanged. Rewrite only structured dumping-ID history references and preserve
an old -> new audit mapping in the changed history entry.
"""
from django.db import migrations, models
from django.db.models import Max


def _old_id(container, labs):
    if container.lab_id and container.lab_number:
        return f'{labs[container.lab_id]} PC-{container.lab_number:05d}'
    return f'PC-{container.pk:06d}'


def _new_id(container, labs):
    if container.lab_id and container.lab_number:
        return f'{labs[container.lab_id]} DC-{container.lab_number:05d}'
    return f'DC-{container.pk:06d}'


def _update_history(history, old_id, new_id):
    """Rename only IDs stored as disposal references, not arbitrary user prose."""
    original_summary = history.summary or ''
    summary = original_summary
    for before, after in (
        (f' disposed into {old_id}', f' disposed into {new_id}'),
        (f'Container {old_id} disposal undone', f'Container {new_id} disposal undone'),
        (f'Dumping container {old_id} restored', f'Dumping container {new_id} restored'),
    ):
        if before in summary:
            summary = summary.replace(before, after)

    details = dict(history.details or {})
    changed = summary != original_summary
    if details.get('dumping_container_id') == old_id:
        details['dumping_container_id'] = new_id
        changed = True
    replacements = []
    for item in details.get('changes', []):
        if not isinstance(item, dict) or item.get('field') != 'Container ID':
            replacements.append(item)
            continue
        new_item = dict(item)
        for field in ('before', 'after'):
            if new_item.get(field) == old_id:
                new_item[field] = new_id
                changed = True
        replacements.append(new_item)
    if changed:
        if 'changes' in details:
            details['changes'] = replacements
        # Retain the old identifier for audit/physical cross-reference.
        renames = list(details.get('container_id_renames') or [])
        if not any(entry.get('before') == old_id and entry.get('after') == new_id for entry in renames):
            renames.append({'before': old_id, 'after': new_id})
        details['container_id_renames'] = renames
        history.summary = summary
        history.details = details
        history.save(update_fields=['summary', 'details'])


def renumber_dumping_containers(apps, schema_editor):
    Lab = apps.get_model('accounts', 'Lab')
    Container = apps.get_model('problem_samples', 'ProblemContainer')
    History = apps.get_model('problem_samples', 'ProblemHistory')
    db = schema_editor.connection.alias
    labs = dict(Lab.objects.using(db).values_list('id', 'code'))

    for lab_id in labs:
        # Preserve all existing PC numbers, including gaps left by dumping
        # containers. Do not re-label physical boxes already in circulation.
        physical_max = (Container.objects.using(db).filter(lab_id=lab_id, is_dumping=False)
                        .aggregate(number=Max('lab_number'))['number'] or 0)
        lab = Lab.objects.using(db).get(pk=lab_id)
        if lab.next_container_number <= physical_max:
            lab.next_container_number = physical_max + 1
            lab.save(update_fields=['next_container_number'])

        dumps = list(Container.objects.using(db).filter(lab_id=lab_id, is_dumping=True)
                     .order_by('created_at', 'pk'))
        for number, dump in enumerate(dumps, 1):
            old_id = _old_id(dump, labs)
            dump.lab_number = number
            dump.save(update_fields=['lab_number'])
            new_id = _new_id(dump, labs)
            if old_id == new_id:
                continue
            # Dumping transfer histories are associated with the tickets that
            # were moved. This remains true even when they have since been
            # restored to other containers or had their lab changed.
            ticket_ids = dump.dumped_sample_ids or []
            if ticket_ids:
                for history in History.objects.using(db).filter(problem_id__in=ticket_ids).iterator():
                    _update_history(history, old_id, new_id)
        lab.next_dumping_container_number = len(dumps) + 1
        lab.save(update_fields=['next_dumping_container_number'])

    # Very old lab-less records show their globally unique PK as identifier;
    # the new DC property/lookup switches their prefix without changing PK.
    for dump in Container.objects.using(db).filter(lab__isnull=True, is_dumping=True).iterator():
        old_id, new_id = _old_id(dump, labs), _new_id(dump, labs)
        if old_id != new_id and dump.dumped_sample_ids:
            for history in History.objects.using(db).filter(problem_id__in=dump.dumped_sample_ids).iterator():
                _update_history(history, old_id, new_id)


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0009_merge_lab_id_and_dumping_counter'),
        ('problem_samples', '0095_rename_cs_follow_up_workflow'),
    ]
    operations = [
        migrations.RemoveConstraint(
            model_name='problemcontainer', name='unique_container_number_per_lab',
        ),
        migrations.RunPython(renumber_dumping_containers),  # Irreversible: old IDs may be printed on labels.
        migrations.AddConstraint(
            model_name='problemcontainer',
            constraint=models.UniqueConstraint(fields=['lab', 'is_dumping', 'lab_number'],
                                               name='unique_container_number_per_lab_and_type'),
        ),
    ]
