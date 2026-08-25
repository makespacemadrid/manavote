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
        (SELECT COUNT(*) FROM comments c WHERE c.member_id = m.id) AS comment_count,
        (SELECT COUNT(*) FROM poll_votes pv WHERE pv.member_id = m.id) AS poll_vote_count,
        (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id) AS poll_count
    FROM members m
    ORDER BY proposal_vote_count DESC, poll_vote_count DESC, proposal_count DESC, m.username ASC
    LIMIT ? OFFSET ?
"""


def user_statistics_query(limit: int, offset: int) -> tuple[str, tuple[Any, ...]]:
    """Return the canonical paginated query used by REST and MCP."""

    return USER_STATISTICS_SELECT_SQL, (limit, offset)
