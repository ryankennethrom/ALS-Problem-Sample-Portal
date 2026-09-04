from datetime import date, datetime, time

from rest_framework.exceptions import ValidationError

from .models import ProblemColumn, SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY, SYSTEM_TRACKING_LINK_FIELD_KEY, SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY
from .search import score_record


TEXT_TYPES = {
    ProblemColumn.TYPE_TEXT,
    ProblemColumn.TYPE_LONG_TEXT,
    ProblemColumn.TYPE_EMAIL,
    ProblemColumn.TYPE_URL,
    ProblemColumn.TYPE_FIXED,
    ProblemColumn.TYPE_DISTRIBUTOR,
    ProblemColumn.TYPE_END_USER,
    ProblemColumn.TYPE_CLIENT_EMAIL,
    ProblemColumn.TYPE_ROW_CREATOR,
    ProblemColumn.TYPE_RECENT_ROW_MODIFIER,
    ProblemColumn.TYPE_BRAND,
}
NUMBER_TYPES = {ProblemColumn.TYPE_NUMBER}
DATE_TYPES = {ProblemColumn.TYPE_DATE, ProblemColumn.TYPE_DATETIME, ProblemColumn.TYPE_TIME}
CHOICE_TYPES = {ProblemColumn.TYPE_CHOICE, ProblemColumn.TYPE_GROUP}
MULTI_CHOICE_TYPES = {ProblemColumn.TYPE_MULTI_CHOICE}
BOOLEAN_TYPES = {ProblemColumn.TYPE_BOOLEAN}

EMPTY_OPERATORS = {'is_empty', 'is_not_empty'}

ALLOWED_OPERATORS = {
    'text': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'number': {'equals', 'not_equals', 'gt', 'gte', 'lt', 'lte', 'between', *EMPTY_OPERATORS},
    'choice': {'equals', 'not_equals', *EMPTY_OPERATORS},
    'multi_choice': {'contains', 'not_contains', *EMPTY_OPERATORS},
    'date': {'equals', 'not_equals', 'before', 'after', 'between', *EMPTY_OPERATORS},
    'datetime': {'equals', 'not_equals', 'before', 'after', 'between', *EMPTY_OPERATORS},
    'time': {'equals', 'not_equals', 'before', 'after', 'between', *EMPTY_OPERATORS},
    'boolean': {'equals'},
    'email': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'url': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'fixed': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'group': {'equals', 'not_equals', *EMPTY_OPERATORS},
    'distributor': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'end_user': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'client_email': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'row_creator': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'recent_row_modifier': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
    'brand': {'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', *EMPTY_OPERATORS},
}


def _empty(value):
    return value is None or value == '' or value == []


def _value_for(problem, column):
    if column.field_key == 'problem-id':
        return problem.problem_number
    if column.field_key == SYSTEM_DAYS_UNTIL_AUTOMATIC_DISPOSAL_FIELD_KEY:
        return problem.days_until_automatic_disposal
    if column.field_key == SYSTEM_TRACKING_LINK_FIELD_KEY:
        return f'/track/{problem.acknowledgement_token}' if problem.acknowledgement_token else ''
    if column.field_key == SYSTEM_TRACKING_LINK_EXPIRY_FIELD_KEY:
        expiry = problem.tracking_link_expires_at
        return expiry.isoformat() if expiry else ''
    if column.column_type == ProblemColumn.TYPE_FIXED:
        return column.default_value
    value = (problem.custom_values or {}).get(column.field_key)
    if column.column_type == ProblemColumn.TYPE_ROW_CREATOR and _empty(value):
        creator = getattr(problem, 'created_by', None)
        return (getattr(creator, 'email', '') or getattr(creator, 'username', '') or problem.legacy_created_by or '').strip()
    if column.column_type == ProblemColumn.TYPE_RECENT_ROW_MODIFIER and _empty(value):
        modifier = getattr(problem, 'modified_by', None)
        creator = getattr(problem, 'created_by', None)
        return (
            getattr(modifier, 'email', '') or getattr(modifier, 'username', '')
            or problem.legacy_modified_by
            or getattr(creator, 'email', '') or getattr(creator, 'username', '')
            or problem.legacy_created_by or ''
        ).strip()
    return value


def _text(value):
    if isinstance(value, list):
        return ' '.join(str(v) for v in value).strip().casefold()
    return str(value or '').strip().casefold()


def _number(value, label='value'):
    try:
        if isinstance(value, bool):
            raise ValueError
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError({label: 'Must be a number.'})


def _temporal(value, kind, label='value'):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({label: 'A value is required.'})
    raw = value.strip()
    try:
        if kind == ProblemColumn.TYPE_DATE:
            return date.fromisoformat(raw)
        if kind == ProblemColumn.TYPE_TIME:
            return time.fromisoformat(raw)
        if kind == ProblemColumn.TYPE_DATETIME:
            return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        pass
    raise ValidationError({label: f'Invalid {kind} value.'})


def _boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {'true', '1', 'yes'}:
            return True
        if lowered in {'false', '0', 'no'}:
            return False
    raise ValidationError({'value': 'Must be Yes or No.'})


def _compare(actual, column, operator, value=None, value2=None):
    if operator == 'is_empty':
        return _empty(actual)
    if operator == 'is_not_empty':
        return not _empty(actual)

    if _empty(actual):
        return False

    kind = column.column_type

    if kind in TEXT_TYPES:
        left = _text(actual)
        right = _text(value)
        if operator == 'contains':
            return right in left
        if operator == 'not_contains':
            return right not in left
        if operator == 'equals':
            return left == right
        if operator == 'not_equals':
            return left != right
        if operator == 'starts_with':
            return left.startswith(right)
        if operator == 'ends_with':
            return left.endswith(right)

    if kind in NUMBER_TYPES:
        left = _number(actual, 'stored_value')
        right = _number(value)
        if operator == 'equals':
            return left == right
        if operator == 'not_equals':
            return left != right
        if operator == 'gt':
            return left > right
        if operator == 'gte':
            return left >= right
        if operator == 'lt':
            return left < right
        if operator == 'lte':
            return left <= right
        if operator == 'between':
            upper = _number(value2, 'value2')
            low, high = sorted((right, upper))
            return low <= left <= high

    if kind in CHOICE_TYPES:
        left = str(actual)
        right = str(value or '')
        if operator == 'equals':
            return left == right
        if operator == 'not_equals':
            return left != right

    if kind in MULTI_CHOICE_TYPES:
        items = actual if isinstance(actual, list) else [actual]
        right = str(value or '')
        if operator == 'contains':
            return right in [str(x) for x in items]
        if operator == 'not_contains':
            return right not in [str(x) for x in items]

    if kind in DATE_TYPES:
        left = _temporal(str(actual), kind, 'stored_value')
        right = _temporal(str(value or ''), kind)
        if operator == 'equals':
            return left == right
        if operator == 'not_equals':
            return left != right
        if operator == 'before':
            return left < right
        if operator == 'after':
            return left > right
        if operator == 'between':
            upper = _temporal(str(value2 or ''), kind, 'value2')
            low, high = sorted((right, upper))
            return low <= left <= high

    if kind in BOOLEAN_TYPES:
        return bool(actual) == _boolean(value)

    return False


def validate_quick_filters(table, quick_filters):
    if not isinstance(quick_filters, list):
        raise ValidationError({'quick_filters': 'Must be a list of quick filter conditions.'})
    if len(quick_filters) > 20:
        raise ValidationError({'quick_filters': 'Quick Filters supports up to 20 choice fields.'})

    columns = {column.field_key: column for column in table.columns.all()}
    validated = []
    errors = []

    for index, condition in enumerate(quick_filters):
        if not isinstance(condition, dict):
            errors.append({'index': index, 'detail': 'Quick filter must be an object.'})
            continue
        field_key = str(condition.get('field_key') or '').strip()
        value = condition.get('value')
        column = columns.get(field_key)
        if not column:
            errors.append({'index': index, 'field_key': 'Unknown column.'})
            continue
        if column.column_type != ProblemColumn.TYPE_CHOICE:
            errors.append({'index': index, 'field_key': 'Quick Filters are available only for Choice columns.'})
            continue
        if value in (None, ''):
            continue
        if value not in (column.choices or []):
            errors.append({'index': index, 'value': 'Not a valid choice for this column.'})
            continue
        validated.append((column, value))

    if errors:
        raise ValidationError({'quick_filters': errors})
    return validated


def validate_filters(table, filters):
    if not isinstance(filters, list):
        raise ValidationError({'filters': 'Must be a list of search conditions.'})
    if len(filters) > 20:
        raise ValidationError({'filters': 'Advanced search supports up to 20 conditions.'})

    columns = {column.field_key: column for column in table.columns.all()}
    validated = []
    errors = []

    for index, condition in enumerate(filters):
        if not isinstance(condition, dict):
            errors.append({'index': index, 'detail': 'Condition must be an object.'})
            continue
        field_key = str(condition.get('field_key') or '').strip()
        operator = str(condition.get('operator') or '').strip()
        column = columns.get(field_key)
        if not column:
            errors.append({'index': index, 'field_key': 'Unknown column.'})
            continue
        allowed = ALLOWED_OPERATORS.get(column.column_type, set())
        if operator not in allowed:
            errors.append({'index': index, 'operator': f'Not valid for {column.get_column_type_display()}.'})
            continue
        if operator not in EMPTY_OPERATORS and operator != 'equals' and condition.get('value') in (None, ''):
            errors.append({'index': index, 'value': 'A value is required.'})
            continue
        if operator == 'equals' and column.column_type != ProblemColumn.TYPE_BOOLEAN and condition.get('value') in (None, ''):
            errors.append({'index': index, 'value': 'A value is required.'})
            continue
        if operator == 'between' and condition.get('value2') in (None, ''):
            errors.append({'index': index, 'value2': 'A second value is required for Between.'})
            continue
        validated.append((column, operator, condition.get('value'), condition.get('value2')))

    if errors:
        raise ValidationError({'filters': errors})
    return validated


def advanced_search_problem_samples(queryset, table, filters, match_mode='all', query='', quick_filters=None):
    match_mode = str(match_mode or 'all').lower()
    if match_mode not in {'all', 'any'}:
        raise ValidationError({'match': 'Must be either "all" or "any".'})

    conditions = validate_filters(table, filters)
    quick_conditions = validate_quick_filters(table, quick_filters or [])
    rows = list(queryset.filter(table=table))
    matched = []

    for problem in rows:
        checks = [_compare(_value_for(problem, column), column, operator, value, value2)
                  for column, operator, value, value2 in conditions]
        condition_match = all(checks) if match_mode == 'all' else any(checks)
        if not conditions:
            condition_match = True
        if not condition_match:
            continue

        quick_match = all(
            _compare(_value_for(problem, column), column, 'equals', value)
            for column, value in quick_conditions
        )
        if not quick_match:
            continue

        if query and str(query).strip():
            score = score_record(problem, query)
            if score < 28:
                continue
            problem.search_score = score
        matched.append(problem)

    if query and str(query).strip():
        matched.sort(key=lambda item: getattr(item, 'search_score', 0), reverse=True)
    else:
        matched.sort(key=lambda item: item.problem_number, reverse=True)
    return matched
