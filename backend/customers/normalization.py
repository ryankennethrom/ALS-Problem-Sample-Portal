import re
import unicodedata


def _clean_text(value):
    text = unicodedata.normalize('NFKC', str(value or ''))
    text = text.replace('\u00a0', ' ')
    return ' '.join(text.strip().split())


def normalize_header(value):
    """Canonicalize export headers such as CoyType, Coy Type, Coy-Type, etc."""
    return re.sub(r'[^a-z0-9]+', '', _clean_text(value).casefold())


def normalize_customer_type(value):
    """Return a canonical customer-type label while preserving unknown types."""
    cleaned = _clean_text(value)
    token = re.sub(r'[^a-z0-9]+', '', cleaned.casefold())
    if token == 'distributor':
        return 'Distributor'
    if token == 'enduser':
        return 'End User'
    return cleaned


def customer_type_is(value, expected):
    return normalize_customer_type(value).casefold() == normalize_customer_type(expected).casefold()


def normalize_company_name(value):
    """Normalize a company name for exact/prefix/fuzzy comparison."""
    return _clean_text(value).casefold()


def normalize_brand(value):
    """Normalize an imported Brand value for exact/prefix/fuzzy comparison."""
    return _clean_text(value).casefold()
