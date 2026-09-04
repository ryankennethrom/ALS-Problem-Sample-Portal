import re
import unicodedata
from rapidfuzz.fuzz import WRatio
from django.db.models import Q

TEXT_FIELDS = {
    'source_id': 100,
    'als_tracking_number': 95,
    'courier_tracking_number': 90,
    'distributor': 70,
    'end_user': 70,
    'client_contact_email': 70,
    'problem_type': 65,
    'issue_description': 55,
    'brand': 45,
    'status': 30,
}


def normalize_text(value):
    value = unicodedata.normalize('NFKC', str(value or '')).lower().strip()
    value = re.sub(r'[^\w@.]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def normalize_identifier(value):
    value = unicodedata.normalize('NFKC', str(value or '')).upper()
    return re.sub(r'[^A-Z0-9]', '', value)


def problem_number_from_query(value):
    raw = unicodedata.normalize('NFKC', str(value or ''))
    match = re.fullmatch(r'\s*(?:problem\s*(?:id)?\s*)?#?\s*(\d+)\s*', raw, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def score_record(obj, query):
    nq = normalize_text(query)
    iq = normalize_identifier(query)
    if not nq and not iq:
        return 0.0
    total = 0.0

    # Problem ID is the strongest identifier and is generated per table.
    problem_number_query = problem_number_from_query(query)
    problem_number = getattr(obj, 'problem_number', None)
    if problem_number_query is not None and problem_number == problem_number_query:
        total = max(total, 260)

    problem_iv = normalize_identifier(problem_number or '')
    if iq and problem_iv:
        if iq == problem_iv:
            total = max(total, 220)
        elif iq in problem_iv or problem_iv in iq:
            total = max(total, 165)
        else:
            total = max(total, WRatio(iq, problem_iv) * 1.05)

    for field, boost in [('source_id', 100), ('als_tracking_number', 95), ('courier_tracking_number', 90)]:
        raw = getattr(obj, field, '') or ''
        iv = normalize_identifier(raw)
        if iq and iv:
            if iq == iv:
                total = max(total, boost + 100)
            elif iq in iv or iv in iq:
                total = max(total, boost + 65)
            else:
                total = max(total, WRatio(iq, iv) / 100 * boost)

    for field, weight in TEXT_FIELDS.items():
        value = normalize_text(getattr(obj, field, '') or '')
        if not value:
            continue
        if nq == value:
            candidate = weight + 60
        elif nq in value:
            candidate = weight + 35
        else:
            candidate = WRatio(nq, value) / 100 * weight
        total = max(total, candidate)

    # Table-defined columns participate in search.
    columns = []
    if getattr(obj, 'table_id', None):
        try:
            columns = [c for c in obj.table.columns.all() if c.searchable]
        except Exception:
            columns = []
    values = obj.custom_values or {}
    for column in columns:
        if column.field_key == 'system-days-until-automatic-disposal':
            raw = getattr(obj, 'days_until_automatic_disposal', None)
        elif column.field_key == 'system-tracking-link':
            token = getattr(obj, 'acknowledgement_token', None)
            raw = f'/track/{token}' if token else ''
        elif column.field_key == 'system-tracking-link-expiry':
            expiry = getattr(obj, 'tracking_link_expires_at', None)
            raw = expiry.isoformat() if expiry else ''
        else:
            raw = column.default_value if column.column_type == 'fixed' else values.get(column.field_key)
        if column.column_type == 'row_creator' and raw in (None, '', []):
            creator = getattr(obj, 'created_by', None)
            raw = (getattr(creator, 'email', '') or getattr(creator, 'username', '') or getattr(obj, 'legacy_created_by', '') or '').strip()
        if column.column_type == 'recent_row_modifier' and raw in (None, '', []):
            modifier = getattr(obj, 'modified_by', None)
            creator = getattr(obj, 'created_by', None)
            raw = (
                getattr(modifier, 'email', '') or getattr(modifier, 'username', '')
                or getattr(obj, 'legacy_modified_by', '')
                or getattr(creator, 'email', '') or getattr(creator, 'username', '')
                or getattr(obj, 'legacy_created_by', '') or ''
            ).strip()
        if raw in (None, '', []):
            continue
        if isinstance(raw, list):
            raw = ' '.join(map(str, raw))
        value = normalize_text(raw)
        weight = 62 if column.column_type in {'choice', 'multi_choice', 'email', 'client_email', 'group', 'distributor', 'end_user', 'row_creator', 'recent_row_modifier', 'brand'} else 52
        if nq == value:
            candidate = weight + 55
        elif nq in value:
            candidate = weight + 32
        else:
            candidate = WRatio(nq, value) / 100 * weight
        total = max(total, candidate)

    return round(total, 2)


def search_problem_samples(query, queryset):
    query = (query or '').strip()
    if not query:
        return []
    q = Q()
    for field in TEXT_FIELDS:
        q |= Q(**{f'{field}__icontains': query})
    iq = normalize_identifier(query)
    problem_number_query = problem_number_from_query(query)
    if problem_number_query is not None:
        q |= Q(problem_number=problem_number_query)
    elif iq.isdigit():
        q |= Q(problem_number=int(iq))
    candidates = list(queryset.filter(q)[:250])
    if len(candidates) < 100:
        seen = {x.pk for x in candidates}
        # Broader pass is needed because portable JSON custom-field searching is scored in Python.
        for obj in queryset[:750]:
            if obj.pk not in seen:
                candidates.append(obj)
                seen.add(obj.pk)
    ranked = []
    for obj in candidates:
        score = score_record(obj, query)
        if score >= 28:
            obj.search_score = score
            ranked.append(obj)
    ranked.sort(key=lambda x: x.search_score, reverse=True)
    return ranked[:75]
