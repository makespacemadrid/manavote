"""Proposal vote recording: applies the vote, triggers processing, and emits audit logs."""

import time

from app.repositories.vote_repo import VoteRepository
from app.services import voting_mode_service


def log_proposal_vote_event(
    logger,
    get_setting_value,
    event,
    source,
    proposal_id,
    member_id,
    vote=None,
    reason_code=None,
    latency_ms=None,
):
    logger.info(
        "event=%s source=%s mode=%s proposal_id=%s member_id=%s vote=%s reason_code=%s latency_ms=%s",
        event,
        source,
        voting_mode_service.get_proposal_vote_mode(get_setting_value),
        proposal_id,
        member_id,
        vote,
        reason_code,
        latency_ms,
    )


def record_proposal_vote(get_db, get_setting_value, process_proposal, logger, proposal_id, member_id, vote, source="web"):
    started_at = time.perf_counter()
    if not voting_mode_service.can_record_proposal_vote(get_setting_value, source):
        log_proposal_vote_event(
            logger,
            get_setting_value,
            event="proposal_vote_rejected",
            source=source,
            proposal_id=proposal_id,
            member_id=member_id,
            reason_code="channel_disabled",
            latency_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return False
    conn = get_db()
    try:
        votes = VoteRepository(conn)
        votes.upsert_proposal_vote(proposal_id, member_id, vote)

        c = conn.cursor()
        c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
        status = c.fetchone()
        if status and status["status"] == "active":
            process_proposal(proposal_id)
        log_proposal_vote_event(
            logger,
            get_setting_value,
            event="proposal_vote_accepted",
            source=source,
            proposal_id=proposal_id,
            member_id=member_id,
            vote=vote,
            reason_code="ok",
            latency_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return True
    finally:
        conn.close()
