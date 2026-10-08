"""Proposal use cases, independent of HTTP redirects and flashes."""

import logging
import sqlite3
from datetime import datetime

from app.repositories.comment_repo import CommentRepository
from app.repositories.budget_repo import BudgetRepository
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_repo import VoteRepository
from app.db.transactions import write_transaction

logger = logging.getLogger(__name__)


def withdraw_vote(connection, *, proposal_id, member_id, process_proposal):
    repo = ProposalRepository(connection)
    proposal = repo.get_by_id(proposal_id)
    if proposal is not None and proposal["status"] != "active":
        raise ProposalActionError("proposal_processed")
    try:
        VoteRepository(connection).delete_member_vote(proposal_id, member_id)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    # Preserve the missing-proposal no-op and reprocessing even if no vote existed.
    proposal = repo.get_by_id(proposal_id)
    if proposal is not None and proposal["status"] == "active":
        process_proposal(proposal_id)
    logger.info("event=proposal_vote_withdrawn actor_id=%s proposal_id=%s reason_code=ok", member_id, proposal_id)


def undo_approval(connection, *, proposal_id, member_id, is_admin,
                  process_proposal, check_over_budget_proposals):
    if not is_admin:
        raise ProposalActionError("admin_required")
    repo = ProposalRepository(connection)
    budget = BudgetRepository(connection)
    with write_transaction(connection):
        proposal = repo.get_by_id(proposal_id)
        if proposal is None or proposal["status"] != "approved":
            return False
        restored_budget = budget.current_budget() + proposal["amount"]
        repo.reset_approval(proposal_id)
        SettingsRepository(connection).set_value("current_budget", restored_budget)
        budget.add_log(proposal["amount"], f"Undo approval: {proposal['title']}", proposal_id=proposal_id)
    # These callbacks use their own connections and may immediately approve again.
    process_proposal(proposal_id)
    check_over_budget_proposals()
    logger.info("event=proposal_approval_undone actor_id=%s proposal_id=%s reason_code=ok", member_id, proposal_id)
    return True


class ProposalActionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def set_purchase_state(connection, *, proposal_id, member_id, purchased, now=None):
    """Existing policy: any signed-in member may change an approved purchase flag."""
    repo = ProposalRepository(connection)
    proposal = repo.get_by_id(proposal_id)
    if proposal is None:
        raise ProposalActionError("proposal_not_found")
    if proposal["status"] != "approved":
        raise ProposalActionError("proposal_not_approved")
    purchased_at = (now if now is not None else datetime.now()).isoformat() if purchased else None
    try:
        repo.set_purchased_at(proposal_id, purchased_at)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    logger.info(
        "event=proposal_purchase_updated actor_id=%s proposal_id=%s purchased=%s reason_code=ok",
        member_id, proposal_id, purchased,
    )


def delete_proposal(connection, *, proposal_id, member_id, is_admin):
    repo = ProposalRepository(connection)
    proposal = repo.get_by_id(proposal_id)
    if proposal is None:
        raise ProposalActionError("proposal_not_found")
    if proposal["status"] != "active":
        raise ProposalActionError("proposal_processed")
    if proposal["created_by"] != member_id and not is_admin:
        raise ProposalActionError("proposal_owner_required")
    try:
        VoteRepository(connection).delete_for_proposal(proposal_id)
        CommentRepository(connection).delete_for_proposal(proposal_id)
        repo.delete(proposal_id)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    logger.info("event=proposal_deleted actor_id=%s proposal_id=%s reason_code=ok", member_id, proposal_id)


def delete_comment(connection, *, comment_id, member_id, is_admin):
    if not is_admin:
        raise ProposalActionError("admin_required")
    repo = CommentRepository(connection)
    comment = repo.get_by_id(comment_id)
    if comment is None:
        raise ProposalActionError("comment_not_found")
    try:
        repo.delete(comment_id)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    logger.info(
        "event=proposal_comment_deleted actor_id=%s proposal_id=%s comment_id=%s reason_code=ok",
        member_id, comment["proposal_id"], comment_id,
    )
    return comment["proposal_id"]


def get_comment_for_edit(connection, *, comment_id, is_admin):
    if not is_admin:
        raise ProposalActionError("admin_required")
    comment = CommentRepository(connection).get_by_id(comment_id)
    if comment is None:
        raise ProposalActionError("comment_not_found")
    return comment


def update_comment(connection, *, comment_id, member_id, is_admin, content):
    comment = get_comment_for_edit(connection, comment_id=comment_id, is_admin=is_admin)
    content = content.strip()
    if not content:
        return {"proposal_id": comment["proposal_id"], "updated": False}
    try:
        CommentRepository(connection).update_content(comment_id, content)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    logger.info(
        "event=proposal_comment_updated actor_id=%s proposal_id=%s comment_id=%s reason_code=ok",
        member_id, comment["proposal_id"], comment_id,
    )
    return {"proposal_id": comment["proposal_id"], "updated": True}


def update_api_proposal(connection, *, proposal_id, title, description, amount, url, basic_supplies):
    proposal = ProposalRepository(connection).get_by_id(proposal_id)
    if proposal is None:
        raise ProposalActionError('proposal_not_found')
    if proposal['status'] != 'active':
        raise ProposalActionError('proposal_processed')
    try:
        ProposalRepository(connection).update_fields(proposal_id, title, description, amount, url, basic_supplies)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise


def get_proposal_for_web_edit(connection, *, proposal_id, member_id, is_admin):
    proposal = ProposalRepository(connection).get_by_id(proposal_id)
    if proposal is None:
        raise ProposalActionError('proposal_not_found')
    if proposal['created_by'] != member_id and not is_admin:
        raise ProposalActionError('proposal_owner_required')
    if proposal['status'] != 'active':
        raise ProposalActionError('proposal_processed')
    return proposal


def create_web_proposal(connection, *, title, description, amount, url, image_filename,
                        member_id, basic_supplies, process_proposal):
    from app.repositories.member_repo import MemberRepository
    proposal_id = ProposalRepository(connection).create(
        title, description, amount, url, member_id, basic_supplies, image_filename,
    )
    VoteRepository(connection).insert_creator_vote(proposal_id, member_id)
    connection.commit()
    process_proposal(proposal_id)
    return proposal_id, MemberRepository(connection).get_by_id(member_id)['username']


def update_web_proposal(connection, *, proposal_id, member_id, is_admin, title, description,
                        amount, url, image_filename, basic_supplies):
    get_proposal_for_web_edit(connection, proposal_id=proposal_id, member_id=member_id, is_admin=is_admin)
    repo = ProposalRepository(connection)
    try:
        repo.update_fields(proposal_id, title, description, amount, url, basic_supplies,
                           image_filename, update_image=True)
        if basic_supplies and amount > 20.0:
            repo.set_basic_supplies(proposal_id, 0)
            CommentRepository(connection).create(proposal_id, member_id, 'Auto-removed basic supplies flag: amount over €20')
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise


def add_comment(connection, *, proposal_id, member_id, content):
    content = content.strip()
    if not content:
        return False
    CommentRepository(connection).create(proposal_id, member_id, content)
    connection.commit()
    return True


def get_proposal_for_api_edit(connection, proposal_id):
    proposal = ProposalRepository(connection).get_by_id(proposal_id)
    if proposal is None:
        raise ProposalActionError('proposal_not_found')
    if proposal['status'] != 'active':
        raise ProposalActionError('proposal_processed')
    return proposal
