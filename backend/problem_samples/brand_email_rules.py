"""Brand-triggered customer CC and monthly report matching.

Company Brand values are resolved against the current Customer Export, not the
company name in the ticket. Unlisted companies have no inferred Brand.
"""
import re
from customers.models import Customer
from .models import ProblemColumn


def brand_matches(value, rule):
    name = str(value or '').strip().casefold()
    pattern = str(rule.get('pattern') or '').strip().casefold()
    if not name or not pattern:
        return False
    mode = rule.get('match_type')
    if mode == 'exact': return name == pattern
    if mode == 'contains': return pattern in name
    if mode == 'starts_with': return name.startswith(pattern)
    if mode == 'ends_with': return name.endswith(pattern)
    if mode == 'wildcard':
        return re.fullmatch(re.escape(pattern).replace(r'\*', '.*').replace(r'\?', '.'), name) is not None
    return False


def brand_values_by_source(column, values, *, company_cache=None):
    """Return source ID -> distinct Brand values; skip nonexistent company matches."""
    values = values or {}
    sources = {'ticket': [str(values.get(column.field_key) or '')]}
    company_columns = {str(other.pk): other for other in column.table.columns.all()
                       if other.column_type in {ProblemColumn.TYPE_DISTRIBUTOR, ProblemColumn.TYPE_END_USER}}
    if company_cache is None:
        company_cache = {}
    for column_id in column.company_brand_dependencies or []:
        company = company_columns.get(str(column_id))
        if not company:
            continue
        name = str(values.get(company.field_key) or '').strip()
        if not name:
            sources[str(column_id)] = []
            continue
        cache_key = (name.casefold(), company.column_type)
        if cache_key not in company_cache:
            # A company can have multiple export rows, possibly different Brands.
            # Filter by company type to disambiguate names shared across roles.
            expected = 'Distributor' if company.column_type == ProblemColumn.TYPE_DISTRIBUTOR else 'End User'
            found = Customer.objects.filter(company_name__iexact=name, customer_type__iexact=expected).exclude(brand='').values_list('brand', flat=True)
            company_cache[cache_key] = list(dict.fromkeys(brand.strip() for brand in found if brand and brand.strip()))
        sources[str(column_id)] = company_cache[cache_key]
    return sources


def rule_matches(column, values, rule, *, company_cache=None):
    if rule.get('pending_brand_review'):
        return False
    sources = brand_values_by_source(column, values, company_cache=company_cache)
    selected = rule.get('sources', ['ticket'])
    return any(brand_matches(brand, rule) for source in selected if source in sources for brand in sources[source])


def brand_cc_recipients(table, values):
    if not table:
        return []
    seen = set()
    recipients = []
    cache = {}
    for column in table.columns.all():
        if column.column_type != ProblemColumn.TYPE_BRAND:
            continue
        for rule in column.brand_cc_rules or []:
            if not isinstance(rule, dict) or not rule_matches(column, values, rule, company_cache=cache):
                continue
            for raw in rule.get('cc_emails') or []:
                email = str(raw or '').strip()
                if email and email.casefold() not in seen:
                    seen.add(email.casefold())
                    recipients.append(email)
    return recipients
