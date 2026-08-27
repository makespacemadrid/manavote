"""Shared voting-settings validation and persistence for REST and MCP.

Both transports let an admin update `poll_vote_mode`, `proposal_vote_mode`, and
`telegram_require_linked_vote` independently (any subset of the three, in one call).
This module owns the actual write so the two transports can't drift on which settings
keys get written or how a boolean gets stored (`"true"`/`"false"` strings, matching the
rest of the settings table) -- validation of the mode strings themselves reuses
`VALID_PROPOSAL_VOTE_MODES` from `proposal_vote_service`, since poll and proposal vote
modes share the same three allowed values.
"""

from app.services.proposal_vote_service import VALID_PROPOSAL_VOTE_MODES as VALID_VOTE_MODES


def apply_voting_settings(conn, poll_vote_mode=None, proposal_vote_mode=None, telegram_require_linked_vote=None):
    """Persist whichever of the three settings are not None. Caller validates first."""
    c = conn.cursor()
    if poll_vote_mode is not None:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('poll_vote_mode', ?)", (poll_vote_mode,))
    if proposal_vote_mode is not None:
        c.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', ?)", (proposal_vote_mode,)
        )
    if telegram_require_linked_vote is not None:
        c.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', ?)",
            ("true" if telegram_require_linked_vote else "false",),
        )
    conn.commit()
