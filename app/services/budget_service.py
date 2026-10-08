from app.repositories.budget_repo import BudgetRepository
from app.repositories.proposal_repo import ProposalRepository


def calculate_min_backers(member_count, amount, basic_supplies, thresholds):
    percentage = (
        thresholds["basic"]
        if basic_supplies
        else thresholds["over50"]
        if amount > 50
        else thresholds["default"]
    )
    return max(1, int(member_count * (percentage / 100)))


def build_budget_page(connection, *, sort_by="date_desc", page=1, per_page=20):
    """Build the cash/pending timeline without owning the caller's connection."""
    budget = BudgetRepository(connection)
    total_items = budget.calendar_count()
    calendar_items = budget.calendar_items(sort_by, per_page, (page - 1) * per_page)
    amounts = ProposalRepository(connection).amounts_by_day()
    cash_days = {row["day"]: row for row in budget.cash_by_day()}
    all_days = sorted(set(cash_days) | set(amounts["pending"]) | set(amounts["approved"]) | set(amounts["proposals"]))
    daily_budget = []
    cash_balance = pending_total = 0
    for day in all_days:
        cash = cash_days.get(day)
        cash_in = 0 if cash is None else (cash["cash_in"] or 0)
        cash_out = 0 if cash is None else (cash["cash_out"] or 0)
        cash_balance += cash_in - cash_out
        pending_total += amounts["pending"].get(day, 0)
        pending_total -= amounts["approved_from_pending"].get(day, 0)
        approved = amounts["approved"].get(day, 0)
        daily_budget.append({
            "day": day,
            "cash_in": cash_in,
            "cash_out": -cash_out if cash_out else 0,
            "approved": -approved if approved else 0,
            "cash_balance": cash_balance,
            "pending": pending_total,
            "proposals": amounts["proposals"].get(day, 0),
        })
    return {
        "calendar_items": calendar_items,
        "daily_budget": daily_budget,
        "current_balance": daily_budget[-1]["cash_balance"] if daily_budget else 0,
        "page": page,
        "total_pages": max(1, (total_items + per_page - 1) // per_page),
    }
