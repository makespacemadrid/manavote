"""Shared "votes valid after id" cutoff for proposals.

Two events make a proposal's existing votes stop counting toward its approval
threshold until each is recast: an admin undoing its approval, and the
proposal sitting active for too long. Both are represented the same way --
`proposals.votes_valid_after_id` freezes out every vote that already exists
at the moment the event fires: only a vote with a strictly greater `id`
(i.e. cast afterward) counts toward the approval threshold. The cutoff only
ever moves forward (a later event always wins).

Vote ids are a monotonically increasing AUTOINCREMENT sequence allocated by
SQLite itself, so comparing them sidesteps every timestamp precision,
timezone, and text-format pitfall that comparing `created_at` strings would
otherwise hit -- including the undo case, where the cutoff is set and then
immediately re-checked in the same request, often within the same
wall-clock second that SQLite's `CURRENT_TIMESTAMP` can represent.
"""

from datetime import datetime, timedelta

STALE_AFTER_DAYS = 60


def _parse_naive(value):
    """Parse a stored timestamp as naive, stripping any explicit offset/'Z' suffix
    a caller (e.g. JS-submitted or OIDC-derived data) may have attached -- this app
    otherwise stores and compares timestamps as naive text throughout."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def is_due_for_age_staleness(created_at, now=None):
    """Whether a still-active proposal has been active long enough (STALE_AFTER_DAYS)
    for its existing votes to go stale."""
    now = now if now is not None else datetime.now()
    return now >= _parse_naive(created_at) + timedelta(days=STALE_AFTER_DAYS)


def apply_age_staleness(proposal_repo, vote_repo, proposal, now=None):
    """Freeze out a still-active proposal's existing votes once it has been
    active for STALE_AFTER_DAYS. Returns the effective votes_valid_after_id to
    count votes against (possibly unchanged, possibly still None).

    One-shot: once a cutoff exists (from this or from an undo), aging never
    bumps it further -- otherwise every later process_proposal() call would
    recompute the cutoff as "the newest vote right now," perpetually freezing
    out the very recast that was supposed to make the proposal countable
    again.
    """
    current = proposal["votes_valid_after_id"]
    if current is not None:
        return current
    if proposal["status"] == "active" and is_due_for_age_staleness(proposal["created_at"], now):
        cutoff = vote_repo.max_vote_id(proposal["id"])
        proposal_repo.bump_votes_valid_after_id(proposal["id"], cutoff)
        return cutoff
    return current


def is_vote_stale(vote_id, votes_valid_after_id):
    return bool(votes_valid_after_id) and vote_id <= votes_valid_after_id
