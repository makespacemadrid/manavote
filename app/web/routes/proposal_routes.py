import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.web.decorators import admin_required, login_required
from app.web.routes import main_routes as legacy

proposal_bp = Blueprint("proposals", __name__)


@proposal_bp.route("/about", endpoint="about")
def about():
    return render_template("about.html", session_lang=session.get("lang", "en"))


@proposal_bp.route("/budget", endpoint="budget")
def budget():
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
        "budget.html",
        calendar_items=calendar_items,
        daily_budget=daily_budget,
        session_lang=session.get("lang", "en"),
        page=page,
        total_pages=total_pages,
    )


@proposal_bp.route("/proposals", endpoint="proposals")
@login_required
def proposals():
    get_db = legacy.get_db
    get_current_budget = legacy.get_current_budget
    get_member_count = legacy.get_member_count
    get_thresholds = legacy.get_thresholds
    calculate_min_backers = legacy.calculate_min_backers
    get_vote_counts = legacy.get_vote_counts
    is_web_proposal_voting_enabled = legacy.is_web_proposal_voting_enabled
    get_proposal_vote_mode = legacy.get_proposal_vote_mode

    conn = get_db()
    c = conn.cursor()

    filter_type = request.args.get("filter", "active")
    now = datetime.now(timezone.utc)
    old_cutoff = (now - timedelta(days=30)).replace(tzinfo=None).isoformat(sep=" ")

    if filter_type == "basic":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.basic_supplies = 1 ORDER BY p.created_at DESC"
        )
    elif filter_type in ("active", "approved", "over_budget"):
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.status = ? ORDER BY p.created_at DESC",
            (filter_type,),
        )
    elif filter_type == "old":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.status = 'active' AND datetime(p.created_at) <= datetime(?) ORDER BY p.created_at DESC",
            (old_cutoff,),
        )
    elif filter_type == "recent":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.status = 'active' AND datetime(p.created_at) > datetime(?) ORDER BY p.created_at DESC",
            (old_cutoff,),
        )
    elif filter_type == "purchased":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.purchased_at IS NOT NULL ORDER BY p.created_at DESC"
        )
    elif filter_type == "not_purchased":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.status = 'approved' AND p.purchased_at IS NULL ORDER BY p.created_at DESC"
        )
    elif filter_type == "expensive":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.amount > 50 AND p.status IN ('active', 'approved') ORDER BY p.created_at DESC"
        )
    elif filter_type == "standard":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.status = 'approved' AND p.basic_supplies = 0 AND p.amount <= 50 ORDER BY p.created_at DESC"
        )
    else:
        c.execute("SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id ORDER BY p.created_at DESC")

    proposals = [dict(row) for row in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM proposals")
    total_count = c.fetchone()[0]

    c.execute("SELECT * FROM activity_log ORDER BY created_at ASC")
    budget_history_asc = [dict(row) for row in c.fetchall()]

    running = 0
    for log in budget_history_asc:
        running += log["amount"]
        log["balance"] = running

    budget_history = list(reversed(budget_history_asc))

    current_budget = get_current_budget()
    member_count = get_member_count()
    thresholds = get_thresholds()

    # Calculate actual vote requirements based on member count and percentage thresholds
    basic_votes = max(1, int(member_count * (thresholds.get("basic", 2) / 100)))
    standard_votes = max(1, int(member_count * (thresholds.get("default", 4) / 100)))
    expensive_votes = max(1, int(member_count * (thresholds.get("over50", 8) / 100)))

    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'active'")
    active_proposals_sum = c.fetchone()[0]
    c.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'active' AND datetime(created_at) <= datetime(?)",
        (old_cutoff,),
    )
    old_proposals_sum = c.fetchone()[0]
    c.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'active' AND datetime(created_at) > datetime(?)",
        (old_cutoff,),
    )
    recent_proposals_sum = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'over_budget'")
    committed = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND purchased_at IS NULL")
    pending_purchase_sum = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE purchased_at IS NOT NULL")
    purchased_sum = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved'")
    approved_sum = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE basic_supplies = 1")
    basic_sum = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND basic_supplies = 0 AND amount <= 50")
    standard_sum = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE amount > 50")
    expensive_sum = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM proposals")
    all_sum = c.fetchone()[0]

    for p in proposals:
        created_at = datetime.fromisoformat(str(p["created_at"]).replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        p["age_days"] = max(0, (now - created_at.astimezone(timezone.utc)).days)
        p["old_age_threshold"] = (p["age_days"] // 30) * 30 if p["status"] == "active" and p["age_days"] >= 30 else None
        p["min_backers"] = calculate_min_backers(
            member_count,
            p["amount"],
            p.get("basic_supplies"),
            thresholds,
        )
        p["approve_count"], p["reject_count"] = get_vote_counts(c, p["id"])
        p["net_votes"] = p["approve_count"] - p["reject_count"]
        c.execute(
            "SELECT vote FROM votes WHERE proposal_id = ? AND member_id = ?",
            (p["id"], session["member_id"]),
        )
        user_vote = c.fetchone()
        p["user_vote"] = user_vote["vote"] if user_vote else None

    conn.close()

    lang = session.get("lang", "en")

    return render_template(
        "proposals.html",
        proposals=proposals,
        filter=filter_type,
        total_count=total_count,
        current_budget=current_budget,
        budget_history=budget_history,
        member_count=member_count,
        active_proposals_sum=active_proposals_sum,
        old_proposals_sum=old_proposals_sum,
        recent_proposals_sum=recent_proposals_sum,
        approved_sum=approved_sum,
        committed=committed,
        pending_purchase_sum=pending_purchase_sum,
        purchased_sum=purchased_sum,
        basic_sum=basic_sum,
        standard_sum=standard_sum,
        expensive_sum=expensive_sum,
        all_sum=all_sum,
        thresholds=thresholds,
        basic_votes=basic_votes,
        standard_votes=standard_votes,
        expensive_votes=expensive_votes,
        session_lang=lang,
        is_web_proposal_vote_enabled=is_web_proposal_voting_enabled(),
        proposal_vote_mode=get_proposal_vote_mode(),
    )


@proposal_bp.route("/proposal/new", methods=["GET", "POST"], endpoint="new_proposal")
@login_required
def new_proposal():
    # Local aliases so the body below (relocated from the legacy main_routes module)
    # can reference these names unchanged; each is re-read from the legacy module on
    # every request rather than imported once, so module-level state and test
    # monkeypatches on main_routes still take effect.
    get_db = legacy.get_db
    get_base_url = legacy.get_base_url
    get_current_budget = legacy.get_current_budget
    get_thresholds = legacy.get_thresholds
    can_record_proposal_vote = legacy.can_record_proposal_vote
    process_proposal = legacy.process_proposal
    send_telegram_message = legacy.send_telegram_message
    detect_image_type = legacy.detect_image_type
    TelegramClient = legacy.TelegramClient
    TELEGRAM_BOT_TOKEN = legacy.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID = legacy.TELEGRAM_CHAT_ID
    TELEGRAM_THREAD_ID = legacy.TELEGRAM_THREAD_ID
    app = legacy.app

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        amount = float(request.form["amount"])
        url = request.form.get("url", "").strip()
        voting_deadline = request.form.get("voting_deadline", "").strip()
        basic_supplies = 1 if request.form.get("basic_supplies") else 0
        if amount <= 0:
            flash("Amount must be positive", "error")
            return redirect(url_for("proposals.new_proposal"))
        deadline_text = ""
        if voting_deadline:
            try:
                deadline_dt = datetime.fromisoformat(voting_deadline)
                deadline_text = deadline_dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                flash("Invalid voting deadline", "error")
                return redirect(url_for("proposals.new_proposal"))

        image_filename = None
        if "image" in request.files:
            image = request.files["image"]
            if image and image.filename:
                ext = image.filename.split(".")[-1].lower()
                if ext in ["jpg", "jpeg", "png"]:
                    image_filename = f"{secrets.token_hex(8)}.{ext}"
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    image.save(filepath)

                    mime_type = detect_image_type(filepath)
                    if mime_type not in ["jpeg", "png"]:
                        os.remove(filepath)
                        flash("Invalid image format", "error")
                        return redirect(url_for("proposals.new_proposal"))

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO proposals (title, description, amount, url, image_filename, created_by, basic_supplies) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                description,
                amount,
                url,
                image_filename,
                session["member_id"],
                basic_supplies,
            ),
        )
        conn.commit()
        proposal_id = c.lastrowid

        if basic_supplies and amount > 20.0:
            c.execute(
                "UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,)
            )
            c.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (
                    proposal_id,
                    session["member_id"],
                    "Auto-removed basic supplies flag: amount over €20",
                ),
            )
            conn.commit()

        c.execute(
            "INSERT INTO votes (proposal_id, member_id, vote) VALUES (?, ?, 'in_favor')",
            (proposal_id, session["member_id"]),
        )
        conn.commit()

        process_proposal(proposal_id)

        c.execute("SELECT username FROM members WHERE id = ?", (session["member_id"],))
        creator = c.fetchone()["username"]
        conn.close()

        base_url = get_base_url()

        deadline_line = f"\n⏰ Vote by: {deadline_text}" if deadline_text else ""
        message = f"*{title}*\n\n🆕 New proposal\nBy: {creator.split('@')[0]}\nAmount: €{amount}{deadline_line}\n\n{description[:200]}{'...' if len(description) > 200 else ''}\n\n👉 {url if url else 'No link'}\n🔗 {base_url}/proposal/{proposal_id}"
        if can_record_proposal_vote("telegram"):
            TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID).send_proposal_vote_message(message, proposal_id)
        else:
            send_telegram_message(message)

        flash("Proposal created!", "success")
        return redirect(url_for("proposals"))

    current_budget = get_current_budget()
    thresholds = get_thresholds()
    return render_template(
        "new_proposal.html",
        current_budget=current_budget,
        thresholds=thresholds,
        session_lang=session.get("lang", "en"),
    )


@proposal_bp.route("/proposal/<int:proposal_id>", methods=["GET", "POST"], endpoint="proposal_detail")
@login_required
def proposal_detail(proposal_id):
    get_db = legacy.get_db
    get_member_count = legacy.get_member_count
    get_current_budget = legacy.get_current_budget
    get_thresholds = legacy.get_thresholds
    calculate_min_backers = legacy.calculate_min_backers
    get_vote_counts = legacy.get_vote_counts
    can_record_proposal_vote = legacy.can_record_proposal_vote
    record_proposal_vote = legacy.record_proposal_vote
    is_web_proposal_voting_enabled = legacy.is_web_proposal_voting_enabled
    get_proposal_vote_mode = legacy.get_proposal_vote_mode

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.id = ?",
        (proposal_id,),
    )
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("proposals"))

    c.execute(
        "SELECT v.*, m.username FROM votes v JOIN members m ON v.member_id = m.id WHERE proposal_id = ?",
        (proposal_id,),
    )
    votes = c.fetchall()

    member_count = get_member_count()
    current_budget = get_current_budget()
    thresholds = get_thresholds()
    min_backers = calculate_min_backers(
        member_count, proposal["amount"], proposal["basic_supplies"], thresholds
    )

    approve_count, reject_count = get_vote_counts(c, proposal_id)
    net_votes = approve_count - reject_count

    if request.method == "POST":
        if "vote" in request.form:
            if not can_record_proposal_vote("web"):
                legacy.log_proposal_vote_event(
                    event="proposal_vote_rejected",
                    source="web",
                    proposal_id=proposal_id,
                    member_id=session.get("member_id"),
                    reason_code="channel_disabled",
                )
                flash("Web voting is disabled by admin", "error")
                conn.close()
                return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))

            vote = request.form["vote"]

            record_proposal_vote(proposal_id, session["member_id"], vote, source="web")
            flash("Vote recorded!", "success")

        elif "comment" in request.form:
            comment = request.form["comment"].strip()
            if comment:
                c.execute(
                    "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                    (proposal_id, session["member_id"], comment),
                )
                conn.commit()
                flash("Comment added!", "success")

        return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))

    c.execute(
        "SELECT vote FROM votes WHERE proposal_id = ? AND member_id = ?",
        (proposal_id, session["member_id"]),
    )
    user_vote = c.fetchone()

    c.execute(
        "SELECT c.*, m.username FROM comments c JOIN members m ON c.member_id = m.id WHERE proposal_id = ? ORDER BY c.created_at DESC",
        (proposal_id,),
    )
    comments = c.fetchall()

    conn.close()

    lang = session.get("lang", "en")

    return render_template(
        "proposal_detail.html",
        proposal=proposal,
        votes=votes,
        comments=comments,
        approve_count=approve_count,
        reject_count=reject_count,
        net_votes=net_votes,
        member_count=member_count,
        min_backers=min_backers,
        current_budget=current_budget,
        user_vote=user_vote["vote"] if user_vote else None,
        thresholds=thresholds,
        session_lang=lang,
        is_web_proposal_vote_enabled=is_web_proposal_voting_enabled(),
        proposal_vote_mode=get_proposal_vote_mode(),
    )


@proposal_bp.route("/comment/<int:comment_id>/edit", methods=["GET", "POST"], endpoint="edit_comment")
@login_required
def edit_comment(comment_id):
    get_db = legacy.get_db

    if not session.get("is_admin"):
        flash("Admin access required", "error")
        return redirect(url_for("proposals"))

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = c.fetchone()

    if not comment:
        conn.close()
        flash("Comment not found", "error")
        return redirect(url_for("proposals"))

    if request.method == "POST":
        content = request.form["content"].strip()
        if content:
            c.execute(
                "UPDATE comments SET content = ? WHERE id = ?", (content, comment_id)
            )
            conn.commit()
            flash("Comment updated!", "success")
        conn.close()
        return redirect(url_for("proposals.proposal_detail", proposal_id=comment["proposal_id"]))

    conn.close()
    return render_template(
        "edit_comment.html",
        comment=comment,
        session_lang=session.get("lang", "en"),
    )


@proposal_bp.route("/comment/<int:comment_id>/delete", methods=["POST"], endpoint="delete_comment")
@login_required
def delete_comment(comment_id):
    get_db = legacy.get_db

    if not session.get("is_admin"):
        flash("Admin access required", "error")
        return redirect(url_for("proposals"))

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = c.fetchone()

    if not comment:
        conn.close()
        flash("Comment not found", "error")
        return redirect(url_for("proposals"))

    proposal_id = comment["proposal_id"]
    c.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()

    flash("Comment deleted!", "success")
    return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))


@proposal_bp.route("/proposal/<int:proposal_id>/delete", methods=["POST"], endpoint="delete_proposal")
@login_required
def delete_proposal(proposal_id):
    get_db = legacy.get_db

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("proposals"))

    if proposal["status"] != "active":
        conn.close()
        flash("Cannot delete processed proposals", "error")
        return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))

    if proposal["created_by"] != session["member_id"] and not session.get("is_admin"):
        conn.close()
        flash("You can only delete your own proposals", "error")
        return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))

    c.execute("DELETE FROM votes WHERE proposal_id = ?", (proposal_id,))
    c.execute("DELETE FROM comments WHERE proposal_id = ?", (proposal_id,))
    c.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
    conn.commit()
    conn.close()

    flash("Proposal deleted!", "success")
    return redirect(url_for("proposals"))


@proposal_bp.route("/proposal/<int:proposal_id>/edit", methods=["GET", "POST"], endpoint="edit_proposal")
@login_required
def edit_proposal(proposal_id):
    get_db = legacy.get_db
    get_current_budget = legacy.get_current_budget
    get_thresholds = legacy.get_thresholds
    detect_image_type = legacy.detect_image_type
    app = legacy.app

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("proposals"))

    if proposal["created_by"] != session["member_id"] and not session.get("is_admin"):
        conn.close()
        flash("You can only edit your own proposals", "error")
        return redirect(url_for("proposals"))

    if proposal["status"] != "active":
        conn.close()
        flash("Cannot edit processed proposals", "error")
        return redirect(url_for("proposals"))

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        amount = float(request.form["amount"])
        url = request.form.get("url", "").strip()
        basic_supplies = 1 if request.form.get("basic_supplies") else 0
        if amount <= 0:
            flash("Amount must be positive", "error")
            return redirect(url_for("proposals.edit_proposal", proposal_id=proposal_id))

        image_filename = proposal["image_filename"]
        if "image" in request.files:
            image = request.files["image"]
            if image and image.filename:
                ext = image.filename.split(".")[-1].lower()
                if ext in ["jpg", "jpeg", "png"]:
                    if image_filename and os.path.exists(
                        os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    ):
                        os.remove(
                            os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                        )
                    image_filename = f"{secrets.token_hex(8)}.{ext}"
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    image.save(filepath)

                    mime_type = detect_image_type(filepath)
                    if mime_type not in ["jpeg", "png"]:
                        os.remove(filepath)
                        flash("Invalid image format", "error")
                        return redirect(
                            url_for("proposals.edit_proposal", proposal_id=proposal_id)
                        )

        c.execute(
            "UPDATE proposals SET title = ?, description = ?, amount = ?, url = ?, image_filename = ?, basic_supplies = ? WHERE id = ?",
            (
                title,
                description,
                amount,
                url,
                image_filename,
                basic_supplies,
                proposal_id,
            ),
        )
        conn.commit()

        if basic_supplies and amount > 20.0:
            c.execute(
                "UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,)
            )
            c.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (
                    proposal_id,
                    session["member_id"],
                    "Auto-removed basic supplies flag: amount over €20",
                ),
            )
            conn.commit()

        conn.close()

        flash("Proposal updated!", "success")
        return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))

    conn.close()
    current_budget = get_current_budget()
    thresholds = get_thresholds()
    return render_template(
        "edit_proposal.html",
        proposal=proposal,
        current_budget=current_budget,
        thresholds=thresholds,
        session_lang=session.get("lang", "en"),
    )


@proposal_bp.route("/vote/<int:proposal_id>", methods=["POST"], endpoint="quick_vote")
@login_required
def quick_vote(proposal_id):
    can_record_proposal_vote = legacy.can_record_proposal_vote
    record_proposal_vote = legacy.record_proposal_vote

    if not can_record_proposal_vote("web"):
        legacy.log_proposal_vote_event(
            event="proposal_vote_rejected",
            source="web",
            proposal_id=proposal_id,
            member_id=session.get("member_id"),
            reason_code="channel_disabled",
        )
        flash("Web voting is disabled by admin", "error")
        return redirect(url_for("proposals"))

    vote = request.form.get("vote")
    record_proposal_vote(proposal_id, session["member_id"], vote, source="web")
    flash("Vote recorded!", "success")
    return redirect(url_for("proposals"))


@proposal_bp.route("/withdraw-vote/<int:proposal_id>", methods=["GET", "POST"], endpoint="withdraw_vote")
@login_required
def withdraw_vote(proposal_id):
    get_db = legacy.get_db
    process_proposal = legacy.process_proposal

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
    status = c.fetchone()

    if status and status["status"] != "active":
        conn.close()
        flash("Cannot withdraw vote on processed proposals", "error")
        return redirect(url_for("proposals"))

    c.execute(
        "DELETE FROM votes WHERE proposal_id = ? AND member_id = ?",
        (proposal_id, session["member_id"]),
    )
    conn.commit()

    c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
    status = c.fetchone()
    if status and status["status"] == "active":
        process_proposal(proposal_id)

    conn.close()

    flash("Vote withdrawn!", "success")
    return redirect(url_for("proposals"))


@proposal_bp.route("/undo/<int:proposal_id>", endpoint="undo_approve")
@login_required
@admin_required
def undo_approve(proposal_id):
    get_db = legacy.get_db
    get_current_budget = legacy.get_current_budget
    process_proposal = legacy.process_proposal
    check_over_budget_proposals = legacy.check_over_budget_proposals

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if proposal and proposal["status"] == "approved":
        c.execute(
            "UPDATE proposals SET status = 'active', processed_at = NULL, purchased_at = NULL WHERE id = ?",
            (proposal_id,),
        )
        c.execute(
            "UPDATE settings SET value = ? WHERE key = 'current_budget'",
            (str(get_current_budget() + proposal["amount"]),),
        )
        c.execute(
            "INSERT INTO activity_log (amount, description, proposal_id) VALUES (?, ?, ?)",
            (proposal["amount"], f"Undo approval: {proposal['title']}", proposal_id),
        )
        conn.commit()
        # Re-process the proposal (may re-approve if thresholds still met)
        process_proposal(proposal_id)
        check_over_budget_proposals()
        flash("Approval undone, budget restored", "success")

    conn.close()
    return redirect(url_for("proposals"))


@proposal_bp.route("/purchase/<int:proposal_id>", methods=["POST"], endpoint="mark_purchased")
@login_required
def mark_purchased(proposal_id):
    get_db = legacy.get_db

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("proposals"))

    if proposal["status"] != "approved":
        conn.close()
        flash("Can only mark approved proposals as purchased", "error")
        return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))

    c.execute(
        "UPDATE proposals SET purchased_at = ? WHERE id = ?",
        (datetime.now().isoformat(), proposal_id),
    )
    conn.commit()
    conn.close()

    flash("Marked as purchased!", "success")
    return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))


@proposal_bp.route("/unpurchase/<int:proposal_id>", methods=["POST"], endpoint="unmark_purchased")
@login_required
def unmark_purchased(proposal_id):
    get_db = legacy.get_db

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("proposals"))

    if proposal["status"] != "approved":
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("proposals"))

    c.execute(
        "UPDATE proposals SET purchased_at = NULL WHERE id = ?",
        (proposal_id,),
    )
    conn.commit()
    conn.close()

    flash("Purchase status removed", "success")
    return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))
