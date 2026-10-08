"""Shared query contract for per-member participation statistics."""

from __future__ import annotations

import json
from typing import Any


# Compatibility exports retain REST/MCP imports while repositories own SQL.
from app.repositories.member_queries import (
    USER_STATISTICS_SELECT_SQL, USER_STATISTICS_ORDER_SQL,
    user_statistics_query, user_statistics_total_query,
)


def user_statistics_rows(rows: list[Any], *, include_email: bool = False) -> list[dict[str, Any]]:
    """Shape statistics rows and keep member email opt-in at every transport."""

    shaped = [dict(row) for row in rows]
    for row in shaped:
        raw_consumption = row.pop("beverage_consumption_json", "[]")
        try:
            row["beverage_consumption"] = json.loads(raw_consumption or "[]")
        except (TypeError, json.JSONDecodeError):
            row["beverage_consumption"] = []
        if not include_email:
            row.pop("email", None)
    return shaped
