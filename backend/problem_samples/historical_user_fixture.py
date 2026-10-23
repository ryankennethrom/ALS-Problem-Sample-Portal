"""Normalize legacy auth.User natural keys for historical-schema upgrades.

Older tracker backups were dumped with natural_primary/natural_foreign keys.
When historical Django User models are reconstructed from migrations, custom
model attributes and methods needed by UserManager's natural-key lookup may be
absent.  In an isolated staging database, assign deterministic numeric primary
keys to the backed-up users, then rewrite *only* relationships whose historical
field targets auth.User.  This operates on a temporary fixture; the original
backup is left unchanged.

No live DB connection or current model imports are used here.
"""
from __future__ import annotations

import json
from pathlib import Path


class HistoricalUserFixtureError(ValueError):
    """The legacy fixture contains inconsistent auth.User references."""


def normalize_user_keys(records, *, fk_fields, m2m_fields=()):
    """Return (normalized_records, stats), modifying the given loaded records.

    fk_fields and m2m_fields contain (model_label, field_name) pairs obtained
    from the *historical* Django app registry. Never guess relationships from
    a JSON array's appearance (ordinary JSONField values can be arrays).
    """
    if not isinstance(records, list):
        raise HistoricalUserFixtureError('Expected a list of fixture records.')
    users = [r for r in records if r.get('model', '').lower() == 'auth.user']
    used_ids = set()
    username_to_pk = {}
    for record in users:
        name = record.get('fields', {}).get('username')
        if not isinstance(name, str) or not name or name in username_to_pk:
            raise HistoricalUserFixtureError('Duplicate or missing auth.User username in backup.')
        pk = record.get('pk')
        if pk is not None:
            # Django's default auth.User primary key is an integer.
            if isinstance(pk, bool) or not isinstance(pk, (str, int)) or not str(pk).isdigit() or int(pk) < 1:
                raise HistoricalUserFixtureError('Invalid auth.User primary key in backup.')
            pk = int(pk)
            if pk in used_ids:
                raise HistoricalUserFixtureError('Duplicate auth.User primary key in backup.')
            used_ids.add(pk)
        username_to_pk[name] = pk
    next_id = max(used_ids, default=0)
    assigned = 0
    for record in users:
        name = record['fields']['username']
        if username_to_pk[name] is None:
            next_id += 1
            while next_id in used_ids:
                next_id += 1
            username_to_pk[name] = next_id
            record['pk'] = next_id
            used_ids.add(next_id)
            assigned += 1
        else:
            record['pk'] = username_to_pk[name]

    fk_fields = {(label.lower(), name) for label, name in fk_fields}
    m2m_fields = {(label.lower(), name) for label, name in m2m_fields}
    changed_refs = 0

    def resolve(value):
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
            name = value[0]
            if name not in username_to_pk:
                raise HistoricalUserFixtureError('Backup references an auth.User not included in the fixture.')
            return username_to_pk[name], True
        if isinstance(value, list):
            raise HistoricalUserFixtureError('Malformed auth.User natural key in fixture.')
        if value is None or value == '':
            return value, False
        if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).isdigit():
            raise HistoricalUserFixtureError('Invalid auth.User foreign key in fixture.')
        if int(value) not in used_ids:
            raise HistoricalUserFixtureError('Backup contains an auth.User ID absent from its user records.')
        return value, False

    for record in records:
        model = str(record.get('model', '')).lower()
        fields = record.get('fields', {})
        for field in list(fields):
            key = (model, field)
            if key in fk_fields:
                fields[field], changed = resolve(fields[field])
                changed_refs += int(changed)
            elif key in m2m_fields:
                values = fields[field]
                if not isinstance(values, list):
                    raise HistoricalUserFixtureError('Malformed auth.User many-to-many relation in fixture.')
                normalized = []
                for item in values:
                    value, changed = resolve(item)
                    normalized.append(value)
                    changed_refs += int(changed)
                fields[field] = normalized
    return records, {'users_assigned_ids': assigned, 'user_relations_normalized': changed_refs}


def historical_user_relation_fields(historical_apps):
    """Discover only relationships to auth.User in the historical schema."""
    fk_fields, m2m_fields = set(), set()
    for model in historical_apps.get_models():
        for field in model._meta.get_fields():
            if not getattr(field, 'concrete', False) or not getattr(field, 'is_relation', False):
                continue
            target = getattr(field, 'related_model', None)
            if target is None or target._meta.label_lower != 'auth.user':
                continue
            pair = (model._meta.label_lower, field.name)
            if getattr(field, 'many_to_many', False):
                m2m_fields.add(pair)
            elif getattr(field, 'many_to_one', False) or getattr(field, 'one_to_one', False):
                fk_fields.add(pair)
    return fk_fields, m2m_fields


def normalize_historical_user_fixture(source_path, target_path, historical_apps):
    """Write a normalized temporary fixture and return aggregate statistics."""
    with open(source_path, encoding='utf-8') as f:
        records = json.load(f)
    fk_fields, m2m_fields = historical_user_relation_fields(historical_apps)
    records, stats = normalize_user_keys(records, fk_fields=fk_fields, m2m_fields=m2m_fields)
    with open(target_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, separators=(',', ':'), ensure_ascii=False)
    return stats
