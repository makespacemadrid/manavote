"""Read models for the member proposal list, independent of Flask."""

from datetime import datetime, timedelta, timezone

from app.repositories.budget_repo import BudgetRepository
from app.repositories.member_repo import MemberRepository
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_repo import VoteRepository
from app.services.budget_service import calculate_min_backers


def build_proposal_page(connection, *, member_id, filter_type="active", now=None):
    """Preserve listing/filter semantics while building the template's read model."""
    now = now if now is not None else datetime.now(timezone.utc)
    old_cutoff = (now - timedelta(days=30)).replace(tzinfo=None).isoformat(sep=" ")
    repo = ProposalRepository(connection)
    votes = VoteRepository(connection)
    proposals = [dict(row) for row in repo.list_for_page(filter_type, old_cutoff)]
    member_count = MemberRepository(connection).count()
    thresholds = SettingsRepository(connection).get_thresholds()
    for proposal in proposals:
        created_at = datetime.fromisoformat(str(proposal["created_at"]).replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = max(0, (now - created_at.astimezone(timezone.utc)).days)
        proposal["age_days"] = age
        proposal["old_age_threshold"] = (age // 30) * 30 if proposal["status"] == "active" and age >= 30 else None
        proposal["min_backers"] = calculate_min_backers(member_count, proposal["amount"], proposal.get("basic_supplies"), thresholds)
        proposal["approve_count"], proposal["reject_count"] = votes.get_counts(proposal["id"])
        proposal["net_votes"] = proposal["approve_count"] - proposal["reject_count"]
        proposal["user_vote"] = votes.get_member_vote(proposal["id"], member_id)

    history = [dict(row) for row in BudgetRepository(connection).history()]
    running = 0
    for entry in history:
        running += entry["amount"]
        entry["balance"] = running
    return {
        "proposals": proposals,
        "filter": filter_type,
        "total_count": repo.count(),
        "current_budget": BudgetRepository(connection).current_budget(),
        "budget_history": list(reversed(history)),
        "member_count": member_count,
        "thresholds": thresholds,
        "basic_votes": max(1, int(member_count * (thresholds.get("basic", 2) / 100))),
        "standard_votes": max(1, int(member_count * (thresholds.get("default", 4) / 100))),
        "expensive_votes": max(1, int(member_count * (thresholds.get("over50", 8) / 100))),
        **repo.page_totals(old_cutoff),
    }


def build_proposal_detail(connection, *, proposal_id, member_id, get_member_count,
                          get_current_budget, get_thresholds, calculate_min_backers, get_vote_counts):
    from app.repositories.comment_repo import CommentRepository
    proposal = ProposalRepository(connection).detail_with_creator(proposal_id)
    if proposal is None:
        return None
    member_count = get_member_count()
    current_budget = get_current_budget()
    thresholds = get_thresholds()
    approve_count, reject_count = get_vote_counts(connection.cursor(), proposal_id)
    return dict(
        proposal=proposal, votes=VoteRepository(connection).list_with_members(proposal_id),
        comments=CommentRepository(connection).list_with_members(proposal_id),
        approve_count=approve_count, reject_count=reject_count, net_votes=approve_count - reject_count,
        member_count=member_count, min_backers=calculate_min_backers(
            member_count, proposal['amount'], proposal['basic_supplies'], thresholds),
        current_budget=current_budget, user_vote=VoteRepository(connection).get_member_vote(proposal_id, member_id),
        thresholds=thresholds,
    )


def validate_api_filters(status, age):
    from app.domain.enums import ProposalStatus
    if age not in {'', 'recent', 'old'}:
        return 'invalid_age_filter', 'age must be one of: recent, old'
    if status and status not in {s.value for s in ProposalStatus}:
        return 'invalid_status_filter', 'invalid status filter'
    if age and status and status != 'active':
        return 'incompatible_proposal_filters', 'age can only be combined with status=active'
    return None
