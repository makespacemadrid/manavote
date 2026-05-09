from flask import Blueprint, redirect, render_template, request, session, url_for

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

proposal_bp = Blueprint("proposals", __name__)


@proposal_bp.route("/about", endpoint="about")
def about():
    return render_template("about.html", session_lang=session.get("lang", "en"))


@proposal_bp.route("/calendar", endpoint="calendar")
def calendar():
    if not session.get("member_id"):
        return redirect(url_for("auth.login"))

    sort_by = request.args.get("sort", "date_desc")
    page = request.args.get("page", 1, type=int)
    per_page = 20

    if sort_by == "date_asc":
        order_clause = "created_at ASC"
    elif sort_by == "amount_desc":
        order_clause = "amount DESC"
    elif sort_by == "amount_asc":
        order_clause = "amount ASC"
    else:
        order_clause = "created_at DESC"

    conn = legacy.get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM proposals")
    total_proposals = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM activity_log")
    total_budget = c.fetchone()[0]

    total_items = total_proposals + total_budget
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    c.execute(
        f"""
        SELECT *
        FROM (
            SELECT id, created_at, amount, 'proposal' AS item_type, title, status, NULL AS description, id AS proposal_id FROM proposals
            UNION ALL
            SELECT id, created_at, amount, 'activity' AS item_type, NULL AS title, NULL AS status, description, proposal_id FROM activity_log
        ) AS calendar_items
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """,
        (per_page, offset),
    )
    calendar_items = c.fetchall()

    pending_by_day = {}
    c.execute(
        "SELECT date(over_budget_at) as day, COALESCE(SUM(amount), 0) as pending FROM proposals WHERE over_budget_at IS NOT NULL GROUP BY day"
    )
    for row in c.fetchall():
        pending_by_day[row[0]] = row[1]

    c.execute(
        """
        SELECT date(created_at) as day, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as cash_in,
               SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as cash_out
        FROM activity_log GROUP BY date(created_at)
    """
    )
    budget_days = set(row[0] for row in c.fetchall())
    over_budget_days = set(pending_by_day.keys())

    approved_by_day = {}
    c.execute(
        "SELECT date(processed_at) as day, COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND processed_at IS NOT NULL GROUP BY day"
    )
    for row in c.fetchall():
        approved_by_day[row[0]] = row[1]

    approved_from_pending_by_day = {}
    c.execute(
        "SELECT date(processed_at) as day, COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND processed_at IS NOT NULL AND over_budget_at IS NOT NULL GROUP BY day"
    )
    for row in c.fetchall():
        approved_from_pending_by_day[row[0]] = row[1]

    c.execute("SELECT date(created_at) as day, COALESCE(SUM(amount), 0) FROM proposals GROUP BY date(created_at)")
    proposals_by_day = {row[0]: row[1] for row in c.fetchall()}

    all_days = sorted(budget_days | set(over_budget_days) | set(approved_by_day.keys()) | set(proposals_by_day.keys()))

    daily_budget = []
    cash_balance = 0
    pending_total = 0
    pending_by_day_lookup = dict(pending_by_day)

    for day in all_days:
        cash_in = 0
        cash_out = 0

        if day in budget_days:
            c.execute(
                """SELECT SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END)
                FROM activity_log WHERE date(created_at) = ?""",
                (day,),
            )
            row = c.fetchone()
            cash_in = row[0] or 0
            cash_out = row[1] or 0
            cash_balance += cash_in - cash_out

        if day in over_budget_days:
            pending_total += pending_by_day_lookup.get(day, 0)

        approved_today = approved_by_day.get(day, 0)
        approved_from_pending_today = approved_from_pending_by_day.get(day, 0)
        pending_total -= approved_from_pending_today

        proposals_count = proposals_by_day.get(day, 0)

        daily_budget.append(
            {
                "day": day,
                "cash_in": cash_in,
                "cash_out": -cash_out if cash_out else 0,
                "approved": -approved_today if approved_today else 0,
                "cash_balance": cash_balance,
                "pending": pending_total,
                "proposals": proposals_count,
            }
        )

    conn.close()
    return render_template(
        "calendar.html",
        calendar_items=calendar_items,
        daily_budget=daily_budget,
        session_lang=session.get("lang", "en"),
        page=page,
        total_pages=total_pages,
    )


@proposal_bp.route("/proposal/new", methods=["GET", "POST"], endpoint="new_proposal")
@login_required
def new_proposal():
    return legacy.new_proposal()


@proposal_bp.route("/proposal/<int:proposal_id>", methods=["GET", "POST"], endpoint="proposal_detail")
@login_required
def proposal_detail(proposal_id):
    return legacy.proposal_detail(proposal_id)


@proposal_bp.route("/comment/<int:comment_id>/edit", methods=["GET", "POST"], endpoint="edit_comment")
@login_required
def edit_comment(comment_id):
    return legacy.edit_comment(comment_id)


@proposal_bp.route("/comment/<int:comment_id>/delete", methods=["POST"], endpoint="delete_comment")
@login_required
def delete_comment(comment_id):
    return legacy.delete_comment(comment_id)


@proposal_bp.route("/proposal/<int:proposal_id>/delete", methods=["POST"], endpoint="delete_proposal")
@login_required
def delete_proposal(proposal_id):
    return legacy.delete_proposal(proposal_id)


@proposal_bp.route("/proposal/<int:proposal_id>/edit", methods=["GET", "POST"], endpoint="edit_proposal")
@login_required
def edit_proposal(proposal_id):
    return legacy.edit_proposal(proposal_id)


@proposal_bp.route("/vote/<int:proposal_id>", methods=["POST"], endpoint="quick_vote")
@login_required
def quick_vote(proposal_id):
    return legacy.quick_vote(proposal_id)


@proposal_bp.route("/withdraw-vote/<int:proposal_id>", methods=["GET", "POST"], endpoint="withdraw_vote")
@login_required
def withdraw_vote(proposal_id):
    return legacy.withdraw_vote(proposal_id)


@proposal_bp.route("/undo/<int:proposal_id>", endpoint="undo_approve")
@login_required
def undo_approve(proposal_id):
    return legacy.undo_approve(proposal_id)


@proposal_bp.route("/purchase/<int:proposal_id>", methods=["POST"], endpoint="mark_purchased")
@login_required
def mark_purchased(proposal_id):
    return legacy.mark_purchased(proposal_id)


@proposal_bp.route("/unpurchase/<int:proposal_id>", methods=["POST"], endpoint="unmark_purchased")
@login_required
def unmark_purchased(proposal_id):
    return legacy.unmark_purchased(proposal_id)
