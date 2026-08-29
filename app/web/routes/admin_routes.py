import json
import os
import sqlite3
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import generate_password_hash

from app.extensions import limiter
from app.services import backup_service, feedback_service
from app.services.settings_service import normalize_public_base_url
from app.services.telegram_link_service import unlink_member_telegram
from app.web.routes.helpers.admin_audit_helpers import log_admin_backup_event, log_telegram_link_event

from app.web.decorators import admin_required, login_required
from app.web.routes import main_routes as legacy
from werkzeug.utils import secure_filename

admin_bp = Blueprint("admin", __name__)


def _admin_redirect_with_tab():
    tab = request.values.get("tab", "members")
    allowed_tabs = {"members", "budget", "polls", "group_purchases", "feedback", "settings"}
    safe_tab = tab if tab in allowed_tabs else "members"
    return redirect(url_for("admin.admin", tab=safe_tab))


def _log_backup_download_rejected(reason_code, backup_type, filename):
    log_admin_backup_event(
        legacy.app.logger,
        event="admin_backup_download_rejected",
        actor_id=session.get("member_id"),
        backup_type=backup_type,
        file_name=filename,
        reason_code=reason_code,
        status="rejected",
    )


@admin_bp.route("/admin", methods=["GET", "POST"], endpoint="admin")
@limiter.exempt
@login_required
@admin_required
def admin():
    # Local aliases so the body below (relocated from the legacy main_routes module)
    # can reference these names unchanged; each is re-read from the legacy module on
    # every request rather than imported once, so runtime overrides (as tests do) and
    # module-level state (like DB_PATH) still take effect.
    get_db = legacy.get_db
    ensure_db_ready = legacy.ensure_db_ready
    close_expired_polls = legacy.close_expired_polls
    build_poll_results_message = legacy.build_poll_results_message
    send_telegram_message = legacy.send_telegram_message
    send_telegram_admin_test_message = legacy.send_telegram_admin_test_message
    sync_telegram_webhook = legacy.sync_telegram_webhook
    get_setting_value = legacy.get_setting_value
    get_setting_float = legacy.get_setting_float
    get_current_budget = legacy.get_current_budget
    get_thresholds = legacy.get_thresholds
    is_registration_enabled = legacy.is_registration_enabled
    check_over_budget_proposals = legacy.check_over_budget_proposals
    DB_PATH = legacy.DB_PATH
    TELEGRAM_ADMIN_ID = legacy.TELEGRAM_ADMIN_ID
    app = legacy.app

    ensure_db_ready()
    conn = get_db()
    c = conn.cursor()
    expired_poll_ids = close_expired_polls(conn)
    for expired_poll_id in expired_poll_ids:
        message = build_poll_results_message(conn, expired_poll_id)
        if message:
            send_telegram_message(message)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_member":
            username = request.form["username"]
            email = request.form.get("email", "").strip().lower() or None
            password = request.form["password"]
            is_admin = 1 if request.form.get("is_admin") else 0
            password_hash = generate_password_hash(password)

            if email and c.execute(
                "SELECT 1 FROM members WHERE lower(email) = lower(?)", (email,)
            ).fetchone():
                flash("Username or email already exists", "error")
            else:
                try:
                    c.execute(
                        "INSERT INTO members (username, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                        (username, email, password_hash, is_admin),
                    )
                    conn.commit()
                    flash(f"Member {username} added!", "success")
                except sqlite3.IntegrityError:
                    flash("Username or email already exists", "error")

        elif action == "edit_member_identity":
            member_id = int(request.form["member_id"])
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower() or None
            if not username:
                flash("Username is required", "error")
            elif email and "@" not in email:
                flash("Enter a valid email address", "error")
            elif c.execute(
                "SELECT 1 FROM members WHERE id != ? AND (username = ? OR (? IS NOT NULL AND lower(email) = lower(?)))",
                (member_id, username, email, email),
            ).fetchone():
                flash("Username or email already exists", "error")
            else:
                c.execute(
                    "UPDATE members SET username = ?, email = ? WHERE id = ?",
                    (username, email, member_id),
                )
                conn.commit()
                if member_id == session["member_id"]:
                    session["username"] = username
                flash("Member account updated!", "success")

        elif action == "remove_member":
            member_id = request.form["member_id"]
            if int(member_id) == session["member_id"]:
                flash("You can't remove yourself", "error")
            else:
                c.execute("DELETE FROM members WHERE id = ?", (member_id,))
                conn.commit()
                flash("Member removed!", "success")

        elif action == "toggle_admin":
            member_id = request.form["member_id"]
            if int(member_id) == session["member_id"]:
                flash("You can't change your own admin role", "error")
            else:
                current_is_admin = c.execute(
                    "SELECT is_admin FROM members WHERE id = ?", (member_id,)
                ).fetchone()["is_admin"]
                new_is_admin = 0 if current_is_admin else 1
                c.execute(
                    "UPDATE members SET is_admin = ? WHERE id = ?",
                    (new_is_admin, member_id),
                )
                conn.commit()
                flash(
                    f"Admin role {'granted' if new_is_admin else 'removed'}!", "success"
                )

        elif action == "unlink_telegram":
            member_id = request.form["member_id"]
            unlink_member_telegram(get_db, int(member_id))
            log_telegram_link_event(
                app.logger,
                event="admin_telegram_unlink",
                actor_id=session.get("member_id"),
                target_member_id=int(member_id),
                source="admin_panel",
                reason_code="manual_unlink",
                status="success",
            )
            flash("Telegram account unlinked.", "success")

        elif action == "trigger_monthly":
            current = get_current_budget()
            monthly = get_setting_float("monthly_topup", 50)
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'current_budget'",
                (str(current + monthly),),
            )
            c.execute(
                "INSERT INTO activity_log (amount, description) VALUES (?, ?)",
                (monthly, "Monthly top-up"),
            )
            conn.commit()
            check_over_budget_proposals()
            flash(
                f"Monthly top-up applied! New budget: €{get_current_budget()}",
                "success",
            )

        elif action == "add_budget":
            amount = float(request.form["amount"])
            description = request.form["description"].strip()
            if amount == 0:
                flash("Amount must be non-zero", "error")
            else:
                current = get_current_budget()
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'current_budget'",
                    (str(current + amount),),
                )
                c.execute(
                    "INSERT INTO activity_log (amount, description) VALUES (?, ?)",
                    (amount, description),
                )
                conn.commit()
                if amount > 0:
                    check_over_budget_proposals()
                flash(
                    f"Budget item recorded: €{amount:.2f}. New balance: €{get_current_budget():.2f}",
                    "success",
                )

        elif action == "update_thresholds":
            basic = request.form.get("threshold_basic", "5")
            over50 = request.form.get("threshold_over50", "20")
            default = request.form.get("threshold_default", "10")
            if basic:
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'threshold_basic'",
                    (basic,),
                )
            if over50:
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'threshold_over50'",
                    (over50,),
                )
            if default:
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'threshold_default'",
                    (default,),
                )
            conn.commit()
            flash("Thresholds updated!", "success")

        elif action == "update_url":
            try:
                base_url = normalize_public_base_url(request.form.get("base_url", ""))
            except ValueError as exc:
                flash(str(exc), "error")
            else:
                if base_url:
                    c.execute(
                        "INSERT INTO settings (key, value) VALUES ('url', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (base_url,),
                    )
                else:
                    c.execute("DELETE FROM settings WHERE key = 'url'")
                conn.commit()
                synced = sync_telegram_webhook(base_url) if base_url else False
                if synced:
                    flash("Base URL updated and Telegram webhook synced!", "success")
                elif base_url:
                    flash("Base URL updated!", "success")
                else:
                    flash("Base URL cleared. Proposal and image links are unavailable.", "success")

        elif action == "sync_telegram_webhook":
            base_url = get_setting_value("url", "").rstrip("/")
            synced = sync_telegram_webhook(base_url)
            if synced:
                flash("Telegram webhook synced!", "success")
            else:
                flash("Could not sync Telegram webhook. Check TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, and Base URL.", "error")

        elif action == "toggle_registration":
            enabled = "true" if request.form.get("registration_enabled") else "false"
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'registration_enabled'",
                (enabled,),
            )
            conn.commit()
            status = "enabled" if enabled == "true" else "disabled"
            flash(f"Self-registration {status}!", "success")

        elif action == "change_user_password":
            member_id = request.form.get("member_id", type=int)
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not member_id or not new_password or not confirm_password:
                flash("All fields are required", "error")
            elif new_password != confirm_password:
                flash("Passwords do not match", "error")
            elif len(new_password) < 4:
                flash("Password must be at least 4 characters", "error")
            else:
                new_hash = generate_password_hash(new_password)
                c.execute(
                    "UPDATE members SET password_hash = ? WHERE id = ?",
                    (new_hash, member_id),
                )
                conn.commit()
                flash(f"Password changed successfully!", "success")

        elif action == "update_timezone":
            selected_timezone = request.form.get("timezone", "Europe/Madrid")
            c.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('timezone', ?)",
                (selected_timezone,),
            )
            conn.commit()
            flash(f"Timezone updated to {selected_timezone}!", "success")

        elif action == "update_poll_vote_mode":
            poll_vote_mode = request.form.get("poll_vote_mode", "both")
            if poll_vote_mode not in ("both", "web_only", "telegram_only"):
                flash("Invalid vote mode", "error")
            else:
                c.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('poll_vote_mode', ?)",
                    (poll_vote_mode,),
                )
                conn.commit()
                flash("Poll vote mode updated", "success")

        elif action == "update_proposal_vote_mode":
            proposal_vote_mode = request.form.get("proposal_vote_mode", "both")
            if proposal_vote_mode not in ("both", "web_only", "telegram_only"):
                flash("Invalid vote mode", "error")
            else:
                c.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', ?)",
                    (proposal_vote_mode,),
                )
                conn.commit()
                flash("Proposal vote mode updated", "success")

        elif action == "update_telegram_linked_vote_requirement":
            require_linked_votes = "true" if request.form.get("telegram_require_linked_vote") == "on" else "false"
            c.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', ?)",
                (require_linked_votes,),
            )
            conn.commit()
            flash("Telegram linked-account vote requirement updated", "success")


        elif action == "create_poll":
            question = request.form.get("question", "").strip()
            raw_options = request.form.get("options", "")
            closes_at_raw = request.form.get("closes_at", "").strip()
            options = [line.strip() for line in raw_options.splitlines() if line.strip()]
            closes_at = None
            if len(question) < 5:
                flash("Poll question must be at least 5 characters", "error")
            elif len(question) > 200:
                flash("Poll question must be 200 characters or fewer", "error")
            elif len(options) < 2:
                flash("Please provide at least 2 poll options", "error")
            elif len(options) > 12:
                flash("Please provide at most 12 poll options", "error")
            elif any(len(o) > 120 for o in options):
                flash("Each option must be 120 characters or fewer", "error")
            elif not closes_at_raw:
                flash("Please provide a poll end date", "error")
            else:
                try:
                    closes_at = datetime.fromisoformat(closes_at_raw)
                except ValueError:
                    flash("Invalid poll end date", "error")
                else:
                    if closes_at <= datetime.now():
                        flash("Poll end date must be in the future", "error")
                        closes_at = None
            if closes_at is not None:
                closes_at_iso = closes_at.isoformat()
                c.execute(
                    "INSERT INTO polls (question, options_json, created_by, status, closes_at) VALUES (?, ?, ?, 'open', ?)",
                    (question, json.dumps(options), session["member_id"], closes_at_iso),
                )
                conn.commit()
                flash("Poll created!", "success")


        elif action == "close_poll":
            poll_id = request.form.get("poll_id", type=int)
            c.execute(
                "UPDATE polls SET status = 'closed', closes_at = ? WHERE id = ?",
                (datetime.now().isoformat(), poll_id),
            )
            conn.commit()
            results_message = build_poll_results_message(conn, poll_id)
            if results_message:
                send_telegram_message(results_message)
            flash("Poll closed", "success")

        elif action == "reopen_poll":
            poll_id = request.form.get("poll_id", type=int)
            c.execute(
                "UPDATE polls SET status = 'open', closes_at = NULL WHERE id = ?",
                (poll_id,),
            )
            conn.commit()
            flash("Poll reopened", "success")

        elif action == "delete_poll":
            poll_id = request.form.get("poll_id", type=int)
            if not poll_id:
                flash("Poll not found", "error")
            else:
                c.execute("DELETE FROM poll_votes WHERE poll_id = ?", (poll_id,))
                c.execute("DELETE FROM polls WHERE id = ?", (poll_id,))
                if c.rowcount == 0:
                    conn.rollback()
                    flash("Poll not found", "error")
                else:
                    conn.commit()
                    flash("Poll deleted", "success")

        elif action in ("send_poll_telegram", "send_poll_telegram_test"):
            poll_id = request.form.get("poll_id", type=int)
            c.execute("SELECT p.*, m.username as creator FROM polls p JOIN members m ON m.id = p.created_by WHERE p.id = ?", (poll_id,))
            poll = c.fetchone()
            if not poll:
                flash("Poll not found", "error")
            else:
                try:
                    options = json.loads(poll["options_json"] or "[]")
                    if options is None:
                        options = []
                except (TypeError, json.JSONDecodeError):
                    options = []
                lines = [f"*{poll['question']}*", "", "📊 New poll", ""]
                for idx, option in enumerate(options, 1):
                    lines.append(f"{idx}. {option}")
                lines.append("")
                if poll["closes_at"]:
                    try:
                        closes_at_display = datetime.fromisoformat(poll["closes_at"]).strftime("%Y-%m-%d %H:%M")
                    except (TypeError, ValueError):
                        closes_at_display = poll["closes_at"]
                    lines.append(f"⏰ Closes: {closes_at_display}")
                    lines.append("")
                lines.append("Tap a button below to vote.")

                if action == "send_poll_telegram_test":
                    if not TELEGRAM_ADMIN_ID:
                        flash("TELEGRAM_ADMIN_ID is not configured", "error")
                    else:
                        sent = send_telegram_admin_test_message("\n".join(lines), poll["id"], options)
                        flash("Poll test sent to TELEGRAM_ADMIN_ID!" if sent else "Failed to send poll test message", "success" if sent else "error")
                else:
                    sent = send_telegram_message("\n".join(lines), poll["id"], options)
                    flash("Poll sent to Telegram!" if sent else "Failed to send poll to Telegram", "success" if sent else "error")

        elif action == "update_feedback_status":
            try:
                feedback_service.update_feedback_status(
                    conn, feedback_id=request.form.get("feedback_id", type=int),
                    status=request.form.get("status", ""), resolved_by=session["member_id"], logger=app.logger,
                )
                flash("Feedback status updated.", "success")
            except feedback_service.FeedbackValidationError as exc:
                flash(str(exc), "error")
        elif action == "backup_db":
            try:
                backup_name, pruned_count = backup_service.backup_db(DB_PATH, keep_days=7)
                log_admin_backup_event(
                    app.logger,
                    event="admin_backup_created",
                    actor_id=session.get("member_id"),
                    backup_type="db",
                    file_name=backup_name,
                    status="ok",
                    pruned_count=pruned_count,
                )
                flash(
                    f"Backup created: {backup_name} (pruned {pruned_count} old backup(s))",
                    "success",
                )
            except backup_service.BACKUP_FAILURES as exc:
                log_admin_backup_event(
                    app.logger,
                    event="admin_backup_failed",
                    actor_id=session.get("member_id"),
                    backup_type="db",
                    reason_code=backup_service.backup_failure_reason(exc),
                    status="failed",
                    error=str(exc),
                )
                flash(f"Backup failed: {exc}", "error")
        elif action == "backup_images":
            try:
                backup_name, pruned_count = backup_service.backup_uploads(
                    app.config["UPLOAD_FOLDER"], keep_days=7
                )
                log_admin_backup_event(
                    app.logger,
                    event="admin_backup_created",
                    actor_id=session.get("member_id"),
                    backup_type="images",
                    file_name=backup_name,
                    status="ok",
                    pruned_count=pruned_count,
                )
                flash(
                    f"Image backup created: {backup_name} (pruned {pruned_count} old backup(s))",
                    "success",
                )
            except backup_service.BACKUP_FAILURES as exc:
                log_admin_backup_event(
                    app.logger,
                    event="admin_backup_failed",
                    actor_id=session.get("member_id"),
                    backup_type="images",
                    reason_code=backup_service.backup_failure_reason(exc),
                    status="failed",
                    error=str(exc),
                )
                flash(f"Image backup failed: {exc}", "error")

    c.execute("SELECT * FROM members ORDER BY created_at")
    members = c.fetchall()

    c.execute("SELECT * FROM activity_log ORDER BY created_at ASC")
    budget_history_asc = [dict(row) for row in c.fetchall()]

    running = 0
    for log in budget_history_asc:
        running += log["amount"]
        log["balance"] = running

    budget_history = list(reversed(budget_history_asc))

    c.execute("""
        SELECT * FROM (
            SELECT
                p.created_at as event_at,
                'proposal_added' as event_type,
                m.username as actor,
                p.id as proposal_id,
                p.title as proposal_title,
                NULL as vote_value
            FROM proposals p
            JOIN members m ON m.id = p.created_by

            UNION ALL

            SELECT
                v.created_at as event_at,
                'member_voted' as event_type,
                m.username as actor,
                p.id as proposal_id,
                p.title as proposal_title,
                v.vote as vote_value
            FROM votes v
            JOIN members m ON m.id = v.member_id
            JOIN proposals p ON p.id = v.proposal_id

            UNION ALL

            SELECT
                p.processed_at as event_at,
                'proposal_approved' as event_type,
                NULL as actor,
                p.id as proposal_id,
                p.title as proposal_title,
                NULL as vote_value
            FROM proposals p
            WHERE p.status = 'approved' AND p.processed_at IS NOT NULL
        )
        WHERE event_at IS NOT NULL
        ORDER BY event_at DESC
        LIMIT 300
    """)
    proposal_history_rows = c.fetchall()

    proposal_history = []
    for row in proposal_history_rows:
        event_type = row["event_type"]
        actor = row["actor"] or "System"
        vote_value = row["vote_value"]

        if event_type == "proposal_added":
            event_label = "Proposal added"
            details = f"Created by {actor}"
        elif event_type == "member_voted":
            event_label = "Member voted"
            vote_label = "in favor" if vote_value == "in_favor" else "against"
            details = f"{actor} voted {vote_label}"
        elif event_type == "proposal_approved":
            event_label = "Proposal approved"
            details = "Approved automatically after reaching threshold"
        else:
            event_label = event_type
            details = ""

        proposal_history.append(
            {
                "created_at": row["event_at"],
                "event_label": event_label,
                "proposal_id": row["proposal_id"],
                "proposal_title": row["proposal_title"],
                "details": details,
            }
        )

    c.execute("""
        SELECT 
            m.id,
            m.username,
            m.email,
            m.is_admin,
            (SELECT COUNT(*) FROM votes v JOIN proposals p ON v.proposal_id = p.id WHERE v.member_id = m.id) as vote_count,
            (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id) as proposal_count,
            (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id AND p.status = 'approved') as approved_count,
            (SELECT COUNT(*) FROM comments c JOIN proposals p ON c.proposal_id = p.id WHERE c.member_id = m.id) as comment_count
        FROM members m
        ORDER BY vote_count DESC, proposal_count DESC
    """)
    member_stats = c.fetchall()

    c.execute("""
        SELECT
            m.id,
            m.username,
            m.email,
            m.is_admin,
            (SELECT COUNT(*) FROM poll_votes pv WHERE pv.member_id = m.id) AS poll_vote_count,
            (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id) AS poll_created_count
        FROM members m
        ORDER BY poll_vote_count DESC, poll_created_count DESC, m.username ASC
    """)
    member_poll_stats = c.fetchall()

    thresholds = get_thresholds()
    registration_enabled = is_registration_enabled()
    current_budget = get_current_budget()

    from app.services.backup_service import BACKUP_ROOT

    backup_dir = BACKUP_ROOT
    os.makedirs(backup_dir, exist_ok=True)
    backup_base = os.path.basename(DB_PATH).replace(".db", "")
    backups = []
    for filename in os.listdir(backup_dir):
        if filename.startswith(f"{backup_base}_") and filename.endswith(".db"):
            backup_path = os.path.join(backup_dir, filename)
            backups.append(
                {
                    "name": filename,
                    "size": os.path.getsize(backup_path),
                    "modified": datetime.fromtimestamp(os.path.getmtime(backup_path)).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    backups.sort(key=lambda item: item["modified"], reverse=True)

    image_backup_dir = backup_dir
    image_backups = []
    if os.path.isdir(image_backup_dir):
        for filename in os.listdir(image_backup_dir):
            if filename.startswith("uploads_") and filename.endswith(".zip"):
                backup_path = os.path.join(image_backup_dir, filename)
                image_backups.append(
                    {
                        "name": filename,
                        "size": os.path.getsize(backup_path),
                        "modified": datetime.fromtimestamp(os.path.getmtime(backup_path)).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
    image_backups.sort(key=lambda item: item["modified"], reverse=True)

    try:
        c.execute("""
            SELECT p.*, m.username as creator,
                   (SELECT COUNT(*) FROM poll_votes pv WHERE pv.poll_id = p.id) as total_votes
            FROM polls p
            JOIN members m ON m.id = p.created_by
            ORDER BY p.created_at DESC
            LIMIT 50
        """)
        polls = [dict(row) for row in c.fetchall()]
    except sqlite3.Error as exc:
        polls = []
        app.logger.warning(
            "admin_page_failure reason_code=poll_list_failed error=%s", exc
        )

    c.execute("""
        SELECT gp.id, gp.title, gp.status, gp.created_at, m.username AS creator
        FROM group_purchases gp
        JOIN members m ON m.id = gp.created_by
        ORDER BY gp.created_at DESC, gp.id DESC
    """)
    group_purchases = [dict(row) for row in c.fetchall()]

    feedback_items = feedback_service.list_feedback(conn, limit=100)

    c.execute("SELECT value FROM settings WHERE key = 'timezone'")
    tz_row = c.fetchone()
    current_timezone = tz_row["value"] if tz_row else "Europe/Madrid"

    requested_tab = request.values.get("tab", "all")
    allowed_tabs = {"all", "members", "budget", "polls", "group_purchases", "feedback", "settings"}
    active_admin_tab = requested_tab if requested_tab in allowed_tabs else "all"

    conn.close()

    return render_template(
        "admin.html",
        members=members,
        member_stats=member_stats,
        member_poll_stats=member_poll_stats,
        budget_history=budget_history,
        proposal_history=proposal_history,
        current_budget=current_budget,
        thresholds=thresholds,
        registration_enabled=registration_enabled,
        current_timezone=current_timezone,
        get_setting_value=get_setting_value,
        session_lang=session.get("lang", "en"),
        backups=backups,
        image_backups=image_backups,
        polls=polls,
        group_purchases=group_purchases,
        feedback_items=feedback_items,
        active_admin_tab=active_admin_tab,
    )



@admin_bp.route("/check-overbudget", endpoint="check_overbudget")
@login_required
def check_overbudget():
    legacy.check_over_budget_proposals()
    return "OK"


@admin_bp.route("/admin/backups/<backup_type>/<filename>", endpoint="download_backup_file")
@legacy.admin_required
def download_backup_file(backup_type, filename):
    from app.services.backup_service import BACKUP_ROOT

    safe_name = secure_filename(filename or "")
    if safe_name != filename:
        _log_backup_download_rejected("invalid_filename", backup_type, filename)
        flash("Invalid backup filename", "error")
        return _admin_redirect_with_tab()

    if backup_type == "db":
        expected_prefix = f"{os.path.basename(legacy.DB_PATH).replace('.db', '')}_"
        valid = safe_name.startswith(expected_prefix) and safe_name.endswith(".db")
    elif backup_type == "images":
        valid = safe_name.startswith("uploads_") and safe_name.endswith(".zip")
    else:
        _log_backup_download_rejected("invalid_backup_type", backup_type, safe_name)
        flash("Invalid backup type", "error")
        return _admin_redirect_with_tab()

    if not valid:
        _log_backup_download_rejected("invalid_backup_file", backup_type, safe_name)
        flash("Invalid backup file", "error")
        return _admin_redirect_with_tab()

    filepath = os.path.join(BACKUP_ROOT, safe_name)
    if not os.path.isfile(filepath):
        _log_backup_download_rejected("backup_not_found", backup_type, safe_name)
        flash("Backup file not found", "error")
        return _admin_redirect_with_tab()

    actor_id = session.get("member_id")
    log_admin_backup_event(
        legacy.app.logger,
        event="admin_backup_download",
        actor_id=actor_id,
        backup_type=backup_type,
        file_name=safe_name,
        status="ok",
        file_size_bytes=os.path.getsize(filepath),
    )

    return send_file(filepath, as_attachment=True, download_name=safe_name)
