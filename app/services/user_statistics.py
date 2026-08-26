"""Shared query contract for per-member participation statistics."""

from __future__ import annotations

from typing import Any


USER_STATISTICS_SELECT_SQL = """
    SELECT
        m.id,
        m.username,
        m.email,
        m.is_admin,
        (SELECT COUNT(*) FROM votes v WHERE v.member_id = m.id) AS proposal_vote_count,
        (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id) AS proposal_count,
        (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id AND p.status = 'approved') AS approved_proposal_count,
        COALESCE((SELECT SUM(p.amount) FROM proposals p WHERE p.created_by = m.id), 0) AS proposed_budget,
        COALESCE((SELECT SUM(p.amount) FROM proposals p WHERE p.created_by = m.id AND p.status = 'approved'), 0) AS approved_proposal_budget,
        CASE
            WHEN COALESCE((SELECT SUM(p.amount) FROM proposals p WHERE p.created_by = m.id), 0) = 0 THEN 0
            ELSE ROUND(
                100.0 * COALESCE((SELECT SUM(p.amount) FROM proposals p WHERE p.created_by = m.id AND p.status = 'approved'), 0)
                / (SELECT SUM(p.amount) FROM proposals p WHERE p.created_by = m.id),
                2
            )
        END AS approved_budget_percentage,
        (SELECT COUNT(*) FROM comments c WHERE c.member_id = m.id) AS comment_count,
        (SELECT COUNT(*) FROM poll_votes pv WHERE pv.member_id = m.id) AS poll_vote_count,
        (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id) AS poll_count,
        (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id AND p.status = 'open') AS open_poll_count,
        (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id AND p.status = 'closed') AS closed_poll_count,
        (SELECT COUNT(*) FROM poll_votes pv JOIN polls p ON p.id = pv.poll_id WHERE p.created_by = m.id) AS created_poll_vote_count,
        CASE
            WHEN (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id) = 0 THEN 0
            ELSE ROUND(
                1.0 * (SELECT COUNT(*) FROM poll_votes pv JOIN polls p ON p.id = pv.poll_id WHERE p.created_by = m.id)
                / (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id),
                2
            )
        END AS average_votes_per_created_poll,
        (SELECT COUNT(*) FROM group_purchases gp WHERE gp.created_by = m.id) AS group_purchase_count,
        (SELECT COUNT(*) FROM group_purchases gp WHERE gp.created_by = m.id AND gp.status = 'open') AS open_group_purchase_count,
        COALESCE((
            SELECT SUM(q.quantity * c.unit_price)
            FROM group_purchases gp
            JOIN group_purchase_components c ON c.group_purchase_id = gp.id
            JOIN group_purchase_quantities q ON q.component_id = c.id
            WHERE gp.created_by = m.id AND q.quantity > 0
        ), 0) AS created_group_purchase_order_value,
        (SELECT COUNT(DISTINCT q.member_id)
          FROM group_purchases gp
          JOIN group_purchase_components c ON c.group_purchase_id = gp.id
          JOIN group_purchase_quantities q ON q.component_id = c.id
          WHERE gp.created_by = m.id AND q.quantity > 0
        ) AS created_group_purchase_participant_count
    FROM members m
"""


USER_STATISTICS_ORDER_SQL = {
    "participation": "proposal_vote_count {direction}, poll_vote_count {direction}, proposal_count {direction}, m.username ASC",
    "proposed_budget": "proposed_budget {direction}, m.username ASC",
    "approved_budget": "approved_proposal_budget {direction}, m.username ASC",
    "approved_budget_percentage": "approved_budget_percentage {direction}, m.username ASC",
    "poll_count": "poll_count {direction}, m.username ASC",
    "created_poll_vote_count": "created_poll_vote_count {direction}, m.username ASC",
    "average_votes_per_created_poll": "average_votes_per_created_poll {direction}, m.username ASC",
    "group_purchase_count": "group_purchase_count {direction}, m.username ASC",
    "created_group_purchase_order_value": "created_group_purchase_order_value {direction}, m.username ASC",
    "created_group_purchase_participant_count": "created_group_purchase_participant_count {direction}, m.username ASC",
    "username": "m.username {direction}",
}


def user_statistics_query(
    limit: int,
    offset: int,
    *,
    username: str | None = None,
    sort_by: str = "participation",
    sort_direction: str = "desc",
) -> tuple[str, tuple[Any, ...]]:
    """Return the canonical paginated query used by REST and MCP."""

    if sort_by not in USER_STATISTICS_ORDER_SQL:
        raise ValueError("unknown user statistics sort field")
    direction = sort_direction.upper()
    if direction not in {"ASC", "DESC"}:
        raise ValueError("unknown user statistics sort direction")

    query = USER_STATISTICS_SELECT_SQL
    params: list[Any] = []
    if username:
        query += " WHERE m.username = ? COLLATE NOCASE\n"
        params.append(username)
    query += " ORDER BY " + USER_STATISTICS_ORDER_SQL[sort_by].format(direction=direction)
    query += "\n LIMIT ? OFFSET ?"
    params.extend((limit, offset))
    return query, tuple(params)


def user_statistics_total_query(username: str | None = None) -> tuple[str, tuple[Any, ...]]:
    """Return a count query using the same member filter as the statistics page."""

    if username:
        return "SELECT COUNT(*) AS total FROM members m WHERE m.username = ? COLLATE NOCASE", (username,)
    return "SELECT COUNT(*) AS total FROM members", ()


def user_statistics_rows(rows: list[Any], *, include_email: bool = False) -> list[dict[str, Any]]:
    """Shape statistics rows and keep member email opt-in at every transport."""

    shaped = [dict(row) for row in rows]
    if not include_email:
        for row in shaped:
            row.pop("email", None)
    return shaped
