"""Normalize legacy Client Email escalation reasons for display, not storage."""
import re

_LEGACY_LABEL = re.compile(r'\[Dependency Field Priority \d+\s+[—-]\s+([^\]\r\n]+)\]')


def display_escalation_reason(reason):
    if not isinstance(reason, str):
        return ''
    if 'Dependency Field Priority' not in reason:
        return reason
    return _LEGACY_LABEL.sub(lambda match: match.group(1), reason)
