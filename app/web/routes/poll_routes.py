import json

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

poll_bp = Blueprint("polls", __name__)


@poll_bp.route("/polls", methods=["GET", "POST"], endpoint="polls_page")
@login_required
def polls_page():
    legacy.ensure_db_ready()
    conn = legacy.get_db()
    c = conn.cursor()
    expired_poll_ids = legacy.close_expired_polls(conn)
    for expired_poll_id in expired_poll_ids:
        message = legacy.build_poll_results_message(conn, expired_poll_id)
        if message:
            legacy.send_telegram_message(message)

    if request.method == "POST":
        if not legacy.is_web_poll_voting_enabled():
            flash("Web voting is disabled by admin", "error")
            conn.close()
            return redirect(url_for("polls.polls_page"))
        poll_id = request.form.get("poll_id", type=int)
        option_index = request.form.get("option_index", type=int)
        if poll_id is None or option_index is None:
            flash("Invalid vote", "error")
        else:
            try:
                c.execute("SELECT options_json, status FROM polls WHERE id = ?", (poll_id,))
                poll_row = c.fetchone()
            except Exception:
                poll_row = None
                flash("Polls are temporarily unavailable", "error")
            if poll_row is not None:
                try:
                    options = json.loads(poll_row["options_json"] or "[]")
                except (TypeError, json.JSONDecodeError):
                    options = []
                if poll_row["status"] != "open":
                    flash("Poll is closed", "error")
                elif option_index < 0 or option_index >= len(options):
                    flash("Invalid poll option", "error")
                elif not options:
                    flash("Poll has invalid options", "error")
                else:
                    c.execute(
                        "INSERT OR REPLACE INTO poll_votes (poll_id, member_id, option_index) VALUES (?, ?, ?)",
                        (poll_id, session["member_id"], option_index),
                    )
                    conn.commit()
                    flash("Poll vote recorded!", "success")

    try:
        c.execute(
            """
            SELECT p.*, m.username as creator
            FROM polls p
            JOIN members m ON m.id = p.created_by
            ORDER BY p.created_at DESC
            """
        )
        poll_rows = c.fetchall()
    except Exception:
        poll_rows = []
        flash("Polls are temporarily unavailable", "error")

    polls = []
    c.execute(
        "SELECT telegram_username, telegram_user_id FROM members WHERE id = ?",
        (session["member_id"],),
    )
    current_member = c.fetchone()
    is_telegram_linked = bool(
        current_member
        and (current_member["telegram_username"] or current_member["telegram_user_id"] is not None)
    )

    for row in poll_rows:
        poll = dict(row)
        try:
            options = json.loads(poll["options_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            options = []
        try:
            c.execute(
                """
                SELECT
                    pv.option_index,
                    pv.created_at,
                    COALESCE(NULLIF(mm.telegram_username, ''), mm.username, '') AS username,
                    CASE
                        WHEN COALESCE(NULLIF(mm.telegram_username, ''), '') = '' THEN 0
                        ELSE 1
                    END AS is_linked_username
                FROM poll_votes pv
                LEFT JOIN members mm ON mm.id = pv.member_id
                WHERE pv.poll_id = ?
                ORDER BY pv.created_at ASC
                """,
                (poll["id"],),
            )
            votes = [dict(v) for v in c.fetchall()]
            c.execute(
                "SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = ?",
                (poll["id"], session["member_id"]),
            )
            own = c.fetchone()
        except Exception:
            votes = []
            own = None
        counts = [0] * len(options)
        for v in votes:
            if v["option_index"] < len(counts):
                counts[v["option_index"]] += 1
        poll["options"] = options
        poll["votes"] = votes
        poll["counts"] = counts
        poll["user_vote"] = own["option_index"] if own else None
        polls.append(poll)

    conn.close()
    return render_template(
        "polls.html",
        polls=polls,
        session_lang=session.get("lang", "en"),
        is_telegram_vote_enabled=legacy.is_telegram_poll_voting_enabled(),
        is_web_vote_enabled=legacy.is_web_poll_voting_enabled(),
        is_telegram_linked=is_telegram_linked,
    )
