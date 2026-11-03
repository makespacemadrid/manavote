"""Read models for the member proposal list, independent of Flask."""

from datetime import datetime, timedelta, timezone

from app.repositories.budget_repo import BudgetRepository
from app.repositories.member_repo import MemberRepository
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_repo import VoteRepository
from app.services.budget_service import calculate_min_backers
from app.services.vote_staleness_service import apply_age_staleness, is_vote_stale


def build_proposal_page(connection, *, member_id, filter_type="active", now=None, query="", sort="newest", page=1, per_page=20, age="", kind=""):
    """Preserve listing/filter semantics while building the template's read model."""
    now = now if now is not None else datetime.now(timezone.utc)
    old_cutoff = (now - timedelta(days=30)).replace(tzinfo=None).isoformat(sep=" ")
    repo = ProposalRepository(connection)
    filter_type = filter_type if filter_type in {"all", "active", "approved", "rejected", "over_budget", "recent", "old", "basic", "standard", "expensive", "purchased", "not_purchased"} else "all"
    query = str(query or "").strip()[:200]
    sort = sort if sort in {"newest", "oldest", "amount_desc", "amount_asc"} else "newest"
    age = age if age in {'recent', 'old'} else ''
    kind = kind if kind in {'basic', 'standard', 'expensive'} else ''
    per_page = max(1, min(100, per_page))
    matching_count = repo.list_for_page(filter_type, old_cutoff, query=query, count=True, age=age, kind=kind)
    total_pages = max(1, (matching_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    votes = VoteRepository(connection)
    proposals = [dict(row) for row in repo.list_for_page(filter_type, old_cutoff, query=query, sort=sort, limit=per_page, offset=(page-1)*per_page, age=age, kind=kind)]
    member_count = MemberRepository(connection).count()
    thresholds = SettingsRepository(connection).get_thresholds()
    for proposal in proposals:
        created_at = datetime.fromisoformat(str(proposal["created_at"]).replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age_days = max(0, (now - created_at.astimezone(timezone.utc)).days)
        proposal["age_days"] = age_days
        proposal["old_age_threshold"] = (age_days // 30) * 30 if proposal["status"] == "active" and age_days >= 30 else None
        proposal["min_backers"] = calculate_min_backers(member_count, proposal["amount"], proposal.get("basic_supplies"), thresholds)
        votes_valid_after_id = apply_age_staleness(repo, votes, proposal)
        proposal["has_stale_votes"] = bool(votes_valid_after_id)
        proposal["approve_count"], proposal["reject_count"] = votes.get_counts(proposal["id"], after_id=votes_valid_after_id)
        proposal["net_votes"] = proposal["approve_count"] - proposal["reject_count"]
        vote_row = votes.get_member_vote_row(proposal["id"], member_id)
        proposal["user_vote"] = vote_row["vote"] if vote_row else None
        proposal["user_vote_is_stale"] = bool(vote_row) and is_vote_stale(vote_row["id"], votes_valid_after_id)
    connection.commit()  # Persist any votes_valid_after_id ratchets from apply_age_staleness above.

    history = [dict(row) for row in BudgetRepository(connection).history()]
    running = 0
    for entry in history:
        running += entry["amount"]
        entry["balance"] = running
    return {
        "proposals": proposals,
        "filter": filter_type, "search_query": query, "proposal_sort": sort,
        "proposal_age": age, "proposal_kind": kind, "matching_count": matching_count, "page": page, "total_pages": total_pages,
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
                          get_current_budget, get_thresholds, calculate_min_backers):
    from app.repositories.comment_repo import CommentRepository
    repo = ProposalRepository(connection)
    proposal = repo.detail_with_creator(proposal_id)
    if proposal is None:
        return None
    member_count = get_member_count()
    current_budget = get_current_budget()
    thresholds = get_thresholds()
    votes_repo = VoteRepository(connection)
    votes_valid_after_id = apply_age_staleness(repo, votes_repo, proposal)
    connection.commit()  # Persist any votes_valid_after_id ratchet from apply_age_staleness above.
    approve_count, reject_count = votes_repo.get_counts(proposal_id, after_id=votes_valid_after_id)
    vote_rows = [dict(row) for row in votes_repo.list_with_members(proposal_id)]
    for row in vote_rows:
        row["is_stale"] = is_vote_stale(row["id"], votes_valid_after_id)
    vote_row = votes_repo.get_member_vote_row(proposal_id, member_id)
    return dict(
        proposal=proposal, votes=vote_rows,
        comments=CommentRepository(connection).list_with_members(proposal_id),
        approve_count=approve_count, reject_count=reject_count, net_votes=approve_count - reject_count,
        member_count=member_count, min_backers=calculate_min_backers(
            member_count, proposal['amount'], proposal['basic_supplies'], thresholds),
        current_budget=current_budget, user_vote=vote_row["vote"] if vote_row else None,
        user_vote_is_stale=bool(vote_row) and is_vote_stale(vote_row["id"], votes_valid_after_id),
        has_stale_votes=bool(votes_valid_after_id),
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
