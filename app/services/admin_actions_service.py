"""Administrator use cases; request/session/rendering remain transport-owned."""
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from werkzeug.security import generate_password_hash

from app.repositories.member_repo import MemberRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.budget_repo import BudgetRepository
from app.repositories.poll_repo import PollRepository
from app.services import backup_service, feedback_service, poll_service
from app.services.audit_service import log_admin_backup_event, log_telegram_link_event
from app.services.settings_service import normalize_public_base_url
from app.services.telegram_link_service import unlink_member_telegram


@dataclass(frozen=True)
class AdminDependencies:
    get_db: Callable
    get_current_budget: Callable
    get_setting_float: Callable
    get_setting_value: Callable
    check_over_budget_proposals: Callable
    sync_telegram_webhook: Callable
    build_poll_results_message: Callable
    send_telegram_message: Callable
    send_telegram_admin_test_message: Callable
    db_path: str
    upload_folder: str
    telegram_admin_id: str
    logger: object


def _optional_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_admin_action(conn, *, data, actor_id, is_admin, dependencies):
    if not is_admin:
        raise PermissionError('Admin access required')
    messages, updated_username = [], None
    def emit_message(text, category):
        messages.append((text, category))
    members, settings = MemberRepository(conn), SettingsRepository(conn)
    budget, polls = BudgetRepository(conn), PollRepository(conn)
    get_db = dependencies.get_db
    get_current_budget = dependencies.get_current_budget
    get_setting_float = dependencies.get_setting_float
    get_setting_value = dependencies.get_setting_value
    check_over_budget_proposals = dependencies.check_over_budget_proposals
    sync_telegram_webhook = dependencies.sync_telegram_webhook
    build_poll_results_message = dependencies.build_poll_results_message
    send_telegram_message = dependencies.send_telegram_message
    send_telegram_admin_test_message = dependencies.send_telegram_admin_test_message
    logger = dependencies.logger
    upload_folder = dependencies.upload_folder
    DB_PATH = dependencies.db_path
    TELEGRAM_ADMIN_ID = dependencies.telegram_admin_id
    try:
        action = data.get("action")

        if action == "add_member":
            username = data["username"]
            email = data.get("email", "").strip().lower() or None
            password = data["password"]
            is_admin = 1 if data.get("is_admin") else 0
            password_hash = generate_password_hash(password)

            if email and members.email_in_use(email, -1):
                emit_message("Username or email already exists", "error")
            else:
                try:
                    members.create_with_email(username, email, password_hash, is_admin)
                    conn.commit()
                    emit_message(f"Member {username} added!", "success")
                except sqlite3.IntegrityError:
                    emit_message("Username or email already exists", "error")

        elif action == "edit_member_identity":
            member_id = int(data["member_id"])
            username = data.get("username", "").strip()
            email = data.get("email", "").strip().lower() or None
            if not username:
                emit_message("Username is required", "error")
            elif email and "@" not in email:
                emit_message("Enter a valid email address", "error")
            elif members.identity_in_use(member_id, username, email):
                emit_message("Username or email already exists", "error")
            else:
                members.update_identity(member_id, username, email)
                conn.commit()
                if member_id == actor_id:
                    updated_username = username
                emit_message("Member account updated!", "success")

        elif action == "remove_member":
            member_id = data["member_id"]
            if int(member_id) == actor_id:
                emit_message("You can't remove yourself", "error")
            else:
                members.delete(member_id)
                conn.commit()
                emit_message("Member removed!", "success")

        elif action == "toggle_admin":
            member_id = data["member_id"]
            if int(member_id) == actor_id:
                emit_message("You can't change your own admin role", "error")
            else:
                current_is_admin = members.get_by_id(member_id)["is_admin"]
                new_is_admin = 0 if current_is_admin else 1
                members.set_admin(member_id, new_is_admin)
                conn.commit()
                emit_message(
                    f"Admin role {'granted' if new_is_admin else 'removed'}!", "success"
                )

        elif action == "unlink_telegram":
            member_id = data["member_id"]
            unlink_member_telegram(get_db, int(member_id))
            log_telegram_link_event(
                logger,
                event="admin_telegram_unlink",
                actor_id=actor_id,
                target_member_id=int(member_id),
                source="admin_panel",
                reason_code="manual_unlink",
                status="success",
            )
            emit_message("Telegram account unlinked.", "success")

        elif action == "trigger_monthly":
            current = get_current_budget()
            monthly = get_setting_float("monthly_topup", 50)
            settings.set_value('current_budget', str(current + monthly))
            budget.add_log(monthly, 'Monthly top-up')
            conn.commit()
            check_over_budget_proposals()
            emit_message(
                f"Monthly top-up applied! New budget: €{get_current_budget()}",
                "success",
            )

        elif action == "add_budget":
            amount = float(data["amount"])
            description = data["description"].strip()
            if amount == 0:
                emit_message("Amount must be non-zero", "error")
            else:
                current = get_current_budget()
                settings.set_value('current_budget', str(current + amount))
                budget.add_log(amount, description)
                conn.commit()
                if amount > 0:
                    check_over_budget_proposals()
                emit_message(
                    f"Budget item recorded: €{amount:.2f}. New balance: €{get_current_budget():.2f}",
                    "success",
                )

        elif action == "update_thresholds":
            basic = data.get("threshold_basic", "5")
            over50 = data.get("threshold_over50", "20")
            default = data.get("threshold_default", "10")
            if basic:
                settings.set_value('threshold_basic', basic)
            if over50:
                settings.set_value('threshold_over50', over50)
            if default:
                settings.set_value('threshold_default', default)
            conn.commit()
            emit_message("Thresholds updated!", "success")

        elif action == "update_url":
            try:
                base_url = normalize_public_base_url(data.get("base_url", ""))
            except ValueError as exc:
                emit_message(str(exc), "error")
            else:
                if base_url:
                    settings.upsert("url", base_url)
                else:
                    settings.delete("url")
                conn.commit()
                synced = sync_telegram_webhook(base_url) if base_url else False
                if synced:
                    emit_message("Base URL updated and Telegram webhook synced!", "success")
                elif base_url:
                    emit_message("Base URL updated!", "success")
                else:
                    emit_message("Base URL cleared. Proposal and image links are unavailable.", "success")

        elif action == "sync_telegram_webhook":
            base_url = get_setting_value("url", "").rstrip("/")
            synced = sync_telegram_webhook(base_url)
            if synced:
                emit_message("Telegram webhook synced!", "success")
            else:
                emit_message("Could not sync Telegram webhook. Check TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, and Base URL.", "error")

        elif action == "toggle_registration":
            enabled = "true" if data.get("registration_enabled") else "false"
            settings.set_value('registration_enabled', enabled)
            conn.commit()
            status = "enabled" if enabled == "true" else "disabled"
            emit_message(f"Self-registration {status}!", "success")

        elif action == "change_user_password":
            member_id = _optional_int(data.get("member_id"))
            new_password = data.get("new_password", "")
            confirm_password = data.get("confirm_password", "")

            if not member_id or not new_password or not confirm_password:
                emit_message("All fields are required", "error")
            elif new_password != confirm_password:
                emit_message("Passwords do not match", "error")
            elif len(new_password) < 4:
                emit_message("Password must be at least 4 characters", "error")
            else:
                new_hash = generate_password_hash(new_password)
                members.set_password_hash(member_id, new_hash)
                conn.commit()
                emit_message(f"Password changed successfully!", "success")

        elif action == "update_timezone":
            selected_timezone = data.get("timezone", "Europe/Madrid")
            settings.upsert('timezone', selected_timezone)
            conn.commit()
            emit_message(f"Timezone updated to {selected_timezone}!", "success")

        elif action == "update_poll_vote_mode":
            poll_vote_mode = data.get("poll_vote_mode", "both")
            if poll_vote_mode not in ("both", "web_only", "telegram_only"):
                emit_message("Invalid vote mode", "error")
            else:
                settings.upsert('poll_vote_mode', poll_vote_mode)
                conn.commit()
                emit_message("Poll vote mode updated", "success")

        elif action == "update_proposal_vote_mode":
            proposal_vote_mode = data.get("proposal_vote_mode", "both")
            if proposal_vote_mode not in ("both", "web_only", "telegram_only"):
                emit_message("Invalid vote mode", "error")
            else:
                settings.upsert('proposal_vote_mode', proposal_vote_mode)
                conn.commit()
                emit_message("Proposal vote mode updated", "success")

        elif action == "update_telegram_linked_vote_requirement":
            require_linked_votes = "true" if data.get("telegram_require_linked_vote") == "on" else "false"
            settings.upsert('telegram_require_linked_vote', require_linked_votes)
            conn.commit()
            emit_message("Telegram linked-account vote requirement updated", "success")


        elif action == "create_poll":
            question = data.get("question", "").strip()
            raw_options = data.get("options", "")
            closes_at_raw = data.get("closes_at", "").strip()
            allow_multiple = data.get("allow_multiple") == "on"
            options = [line.strip() for line in raw_options.splitlines() if line.strip()]
            closes_at = None
            if len(question) < 5:
                emit_message("Poll question must be at least 5 characters", "error")
            elif len(question) > 200:
                emit_message("Poll question must be 200 characters or fewer", "error")
            elif len(options) < 2:
                emit_message("Please provide at least 2 poll options", "error")
            elif len(options) > 12:
                emit_message("Please provide at most 12 poll options", "error")
            elif any(len(o) > 120 for o in options):
                emit_message("Each option must be 120 characters or fewer", "error")
            elif not closes_at_raw:
                emit_message("Please provide a poll end date", "error")
            else:
                try:
                    closes_at = datetime.fromisoformat(closes_at_raw)
                except ValueError:
                    emit_message("Invalid poll end date", "error")
                else:
                    if closes_at <= datetime.now():
                        emit_message("Poll end date must be in the future", "error")
                        closes_at = None
            if closes_at is not None:
                closes_at_iso = closes_at.isoformat()
                poll_id = polls.create_with_deadline(question, json.dumps(options), actor_id, closes_at_iso, allow_multiple)
                conn.commit()
                message = poll_service.build_poll_announcement_message(
                    question, options, closes_at_iso, allow_multiple
                )
                send_telegram_message(message, poll_id, options)
                emit_message("Poll created!", "success")


        elif action == "close_poll":
            poll_id = _optional_int(data.get("poll_id"))
            polls.set_status(poll_id, "closed", datetime.now().isoformat())
            conn.commit()
            results_message = build_poll_results_message(conn, poll_id)
            if results_message:
                send_telegram_message(results_message)
            emit_message("Poll closed", "success")

        elif action == "reopen_poll":
            poll_id = _optional_int(data.get("poll_id"))
            polls.set_status(poll_id, "open", None)
            conn.commit()
            emit_message("Poll reopened", "success")

        elif action == "delete_poll":
            poll_id = _optional_int(data.get("poll_id"))
            if not poll_id:
                emit_message("Poll not found", "error")
            else:
                polls.delete_votes(poll_id)
                deleted = polls.delete(poll_id)
                if deleted == 0:
                    conn.rollback()
                    emit_message("Poll not found", "error")
                else:
                    conn.commit()
                    emit_message("Poll deleted", "success")

        elif action in ("send_poll_telegram", "send_poll_telegram_test"):
            poll_id = _optional_int(data.get("poll_id"))
            poll = polls.detail_with_creator(poll_id)
            if not poll:
                emit_message("Poll not found", "error")
            else:
                try:
                    options = json.loads(poll["options_json"] or "[]")
                    if options is None:
                        options = []
                except (TypeError, json.JSONDecodeError):
                    options = []
                message = poll_service.build_poll_announcement_message(
                    poll["question"], options, poll["closes_at"], bool(poll["allow_multiple"])
                )

                if action == "send_poll_telegram_test":
                    if not TELEGRAM_ADMIN_ID:
                        emit_message("TELEGRAM_ADMIN_ID is not configured", "error")
                    else:
                        sent = send_telegram_admin_test_message(message, poll["id"], options)
                        emit_message("Poll test sent to TELEGRAM_ADMIN_ID!" if sent else "Failed to send poll test message", "success" if sent else "error")
                else:
                    sent = send_telegram_message(message, poll["id"], options)
                    emit_message("Poll sent to Telegram!" if sent else "Failed to send poll to Telegram", "success" if sent else "error")

        elif action == "update_feedback_status":
            try:
                feedback_service.update_feedback_status(
                    conn, feedback_id=_optional_int(data.get("feedback_id")),
                    status=data.get("status", ""), resolved_by=actor_id, logger=logger,
                )
                emit_message("Feedback status updated.", "success")
            except feedback_service.FeedbackValidationError as exc:
                emit_message(str(exc), "error")
        elif action == "backup_db":
            try:
                backup_name, pruned_count = backup_service.backup_db(DB_PATH, keep_days=7)
                log_admin_backup_event(
                    logger,
                    event="admin_backup_created",
                    actor_id=actor_id,
                    backup_type="db",
                    file_name=backup_name,
                    status="ok",
                    pruned_count=pruned_count,
                )
                emit_message(
                    f"Backup created: {backup_name} (pruned {pruned_count} old backup(s))",
                    "success",
                )
            except backup_service.BACKUP_FAILURES as exc:
                log_admin_backup_event(
                    logger,
                    event="admin_backup_failed",
                    actor_id=actor_id,
                    backup_type="db",
                    reason_code=backup_service.backup_failure_reason(exc),
                    status="failed",
                    error=str(exc),
                )
                emit_message(f"Backup failed: {exc}", "error")
        elif action == "backup_images":
            try:
                backup_name, pruned_count = backup_service.backup_uploads(
                    upload_folder, keep_days=7
                )
                log_admin_backup_event(
                    logger,
                    event="admin_backup_created",
                    actor_id=actor_id,
                    backup_type="images",
                    file_name=backup_name,
                    status="ok",
                    pruned_count=pruned_count,
                )
                emit_message(
                    f"Image backup created: {backup_name} (pruned {pruned_count} old backup(s))",
                    "success",
                )
            except backup_service.BACKUP_FAILURES as exc:
                log_admin_backup_event(
                    logger,
                    event="admin_backup_failed",
                    actor_id=actor_id,
                    backup_type="images",
                    reason_code=backup_service.backup_failure_reason(exc),
                    status="failed",
                    error=str(exc),
                )
                emit_message(f"Image backup failed: {exc}", "error")

    except sqlite3.Error:
        conn.rollback()
        raise
    return messages, updated_username
