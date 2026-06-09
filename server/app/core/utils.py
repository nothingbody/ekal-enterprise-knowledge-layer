"""Shared utility functions."""

import re

_LIKE_ESCAPE_RE = re.compile(r'([%_\\])')


def escape_like(value: str) -> str:
    """Escape SQL LIKE/ILIKE wildcard characters (%, _, \\)."""
    return _LIKE_ESCAPE_RE.sub(r'\\\1', value)
