"""Helpers for normalized settings access patterns."""

from urllib.parse import urlsplit


def get_enum_setting(getter, key, default, allowed_values):
    """Read a setting and normalize invalid values to default."""
    value = getter(key, default)
    normalized = str(value).strip().lower()
    if normalized not in allowed_values:
        return default
    return normalized


def normalize_public_base_url(value):
    """Return a safe public HTTPS base URL, or ``None`` when explicitly cleared."""
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Base URL must be a public HTTPS URL without credentials, query, or fragment")
    return normalized
