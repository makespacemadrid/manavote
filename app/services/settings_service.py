"""Helpers for normalized settings access patterns."""


def get_enum_setting(getter, key, default, allowed_values):
    """Read a setting and normalize invalid values to default."""
    value = getter(key, default)
    normalized = str(value).strip().lower()
    if normalized not in allowed_values:
        return default
    return normalized
