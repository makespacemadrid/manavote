import os
import sqlite3
import hashlib
import hmac
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    logging.getLogger(__name__).warning("python-dotenv not installed; skipping .env loading")

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_file,
    jsonify,
)
from app.extensions import limiter, csrf
from app.db.connection import get_db as repo_get_db, set_db_path
from app.db.migrations import run_migrations
from app.integrations.telegram_client import TelegramClient
from app.integrations.bounded_executor import BoundedExecutor
from app.integrations import telegram_agent
from app.integrations.telegram_webhook import (
    classify_message_command,
    dispatch_callback,
    dispatch_message,
    extract_callback_context,
    extract_message_context,
    is_configured_forum_topic,
    is_natural_language_message,
    TelegramUpdateDeduplicator,
)
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_repo import VoteRepository
from app.services.auth_service import verify_and_migrate_password
from app.services.budget_service import calculate_min_backers
from app.services.proposal_service import ProposalService
from app.web.routes.helpers.admin_audit_helpers import log_admin_backup_event, log_telegram_link_event
from app.services.proposal_vote_service import can_record_proposal_vote_source, normalize_proposal_vote_mode
from app.services.settings_service import get_enum_setting
from app.services.telegram_link_service import process_link_command
from app.services.telegram_access_service import get_telegram_principal
from app.web.app_setup import app, BASE_DIR, is_production
from app.web.decorators import login_required, admin_required
from app.web.routes.helpers.main_helpers import (
    detect_image_type,
    format_datetime,
    truncate_username as helper_truncate_username,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import markdown
import warnings
import json
import time


_telegram_agent_executor = BoundedExecutor(
    max_workers=4,
    max_pending=32,
    thread_name_prefix="telegram-agent",
)
_telegram_update_deduplicator = TelegramUpdateDeduplicator(
    connection_factory=lambda: get_db()
)
telegram_agent.configure_pending_action_store(lambda: get_db())
telegram_agent.configure_history_store(lambda: get_db())


@app.template_filter("username")
def truncate_username(username):
    return helper_truncate_username(username)


@app.template_filter("localtime")
def localtime_filter(dt_str, fmt="%Y-%m-%d %H:%M"):
    """Jinja2 filter to format datetime in configured timezone"""
    return format_datetime(dt_str, get_db, fmt)


from translations import TRANSLATIONS


@app.template_filter("markdown")
def render_markdown(text):
    if not text:
        return ""
    return markdown.markdown(text, extensions=["nl2br"])


@app.template_filter("lang")
def get_lang(key):
    from flask import session

    lang = session.get("lang", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)


DB_PATH = os.getenv("APP_DB_PATH", os.path.join(BASE_DIR, "app.db"))
set_db_path(DB_PATH)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID", "")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        telegram_username TEXT,
        telegram_user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        amount REAL NOT NULL,
        url TEXT,
        image_filename TEXT,
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        processed_at TEXT,
        purchased_at TEXT,
        basic_supplies INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        vote TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(proposal_id, member_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        created_by INTEGER,
        proposal_id INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'open',
        closes_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS poll_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        option_index INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(poll_id, member_id)
    )""")

    c.execute("SELECT COUNT(*) FROM members WHERE is_admin = 1")
    if c.fetchone()[0] == 0:
        bootstrap_password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
        if not bootstrap_password:
            if app.config.get("TESTING"):
                bootstrap_password = "test-admin-password"
            elif is_production:
                raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD must be set before first startup in production")
            else:
                bootstrap_password = "change-me-admin-password"
                app.logger.warning(
                    "ADMIN_BOOTSTRAP_PASSWORD is not set; using insecure default for bootstrap admin"
                )
        admin_password = generate_password_hash(bootstrap_password)
        c.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, 1)",
            ("admin", admin_password),
        )

    c.execute("SELECT value FROM settings WHERE key = 'current_budget'")
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO settings (key, value) VALUES ('current_budget', '300')")
        c.execute("INSERT INTO settings (key, value) VALUES ('monthly_topup', '50')")
        c.execute("INSERT INTO settings (key, value) VALUES ('threshold_basic', '5')")
        c.execute("INSERT INTO settings (key, value) VALUES ('threshold_over50', '20')")
        c.execute(
            "INSERT INTO settings (key, value) VALUES ('threshold_default', '10')"
        )
        c.execute(
            "INSERT INTO activity_log (amount, description) VALUES (300, 'Ventas mercadillo marzo')"
        )
        c.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_enabled', 'true')"
        )
    run_migrations(c)

    conn.commit()
    conn.close()


def ensure_db_ready():
    conn = repo_get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
        has_members = c.fetchone() is not None
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        has_settings = c.fetchone() is not None

        if not (has_members and has_settings):
            init_db()
            return

        # Always run migrations for existing databases so newly introduced
        # tables/columns (for example polls) are created before route handlers use them.
        run_migrations(c)
        conn.commit()
    finally:
        conn.close()


def close_expired_polls(conn):
    now_iso = datetime.now().isoformat()
    c = conn.cursor()
    c.execute(
        """
        SELECT id
        FROM polls
        WHERE status = 'open'
          AND closes_at IS NOT NULL
          AND closes_at != ''
          AND closes_at <= ?
        """,
        (now_iso,),
    )
    expired_poll_ids = [row["id"] for row in c.fetchall()]
    if not expired_poll_ids:
        return []
    c.execute(
        """
        UPDATE polls
        SET status = 'closed'
        WHERE status = 'open'
          AND closes_at IS NOT NULL
          AND closes_at != ''
          AND closes_at <= ?
        """,
        (now_iso,),
    )
    if c.rowcount:
        conn.commit()
    return expired_poll_ids


def build_poll_results_message(conn, poll_id):
    c = conn.cursor()
    c.execute("SELECT id, question, closes_at FROM polls WHERE id = ?", (poll_id,))
    poll = c.fetchone()
    if not poll:
        return None
    try:
        closes_display = (
            datetime.fromisoformat(poll["closes_at"]).strftime("%Y-%m-%d %H:%M")
            if poll["closes_at"]
            else "n/a"
        )
    except (TypeError, ValueError):
        closes_display = poll["closes_at"] or "n/a"

    c.execute(
        """
        SELECT pv.option_index, COUNT(*) AS vote_count
        FROM poll_votes pv
        WHERE pv.poll_id = ?
        GROUP BY pv.option_index
        ORDER BY pv.option_index ASC
        """,
        (poll_id,),
    )
    counts = {row["option_index"]: row["vote_count"] for row in c.fetchall()}
    c.execute("SELECT options_json FROM polls WHERE id = ?", (poll_id,))
    options_row = c.fetchone()
    try:
        options = json.loads((options_row["options_json"] if options_row else "[]") or "[]")
    except (TypeError, json.JSONDecodeError):
        options = []

    total_votes = sum(counts.values())
    lines = [f"📊 *Poll closed: #{poll['id']}*", f"*{poll['question']}*", f"⏰ Closed: {closes_display}", ""]
    if not options:
        lines.append("No valid poll options were found.")
        return "\n".join(lines)

    max_count = max([counts.get(idx, 0) for idx in range(len(options))] + [1])
    for idx, option in enumerate(options):
        count = counts.get(idx, 0)
        pct = (count / total_votes * 100.0) if total_votes else 0.0
        bar_len = int(round((count / max_count) * 12)) if max_count else 0
        bar = "█" * bar_len + "░" * (12 - bar_len)
        lines.append(f"{idx + 1}. {option}")
        lines.append(f"`{bar}` {count} vote(s) ({pct:.1f}%)")
    lines.append("")
    lines.append(f"Total votes: *{total_votes}*")
    return "\n".join(lines)


def get_db():
    set_db_path(DB_PATH)
    ensure_db_ready()
    return repo_get_db()


def get_setting_value(key, default=None):
    conn = get_db()
    value = SettingsRepository(conn).get_value(key, default)
    conn.close()
    return value


def get_setting_float(key, default=0.0):
    value = get_setting_value(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def get_base_url():
    url = get_setting_value("url", "")
    if url:
        return url
    if request:
        return request.host_url
    return ""


def get_current_budget():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(amount) as total FROM activity_log")
    total = c.fetchone()["total"]
    conn.close()
    return total if total else 0


def get_member_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM members")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_thresholds():
    conn = get_db()
    thresholds = SettingsRepository(conn).get_thresholds()
    conn.close()
    return thresholds




def get_vote_counts(cursor, proposal_id):
    cursor.execute(
        "SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'in_favor'",
        (proposal_id,),
    )
    approve_count = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'against'",
        (proposal_id,),
    )
    reject_count = cursor.fetchone()[0]
    return approve_count, reject_count


def is_registration_enabled():
    value = get_setting_value("registration_enabled", "true")
    return str(value).lower() == "true"


def get_poll_vote_mode():
    return get_enum_setting(
        get_setting_value,
        "poll_vote_mode",
        "both",
        {"both", "web_only", "telegram_only"},
    )


def is_web_poll_voting_enabled():
    return get_poll_vote_mode() in {"both", "web_only"}


def is_telegram_poll_voting_enabled():
    return get_poll_vote_mode() in {"both", "telegram_only"}


def require_linked_telegram_for_votes():
    return str(get_setting_value("telegram_require_linked_vote", "false")).lower() == "true"


def get_proposal_vote_mode():
    mode = get_enum_setting(
        get_setting_value,
        "proposal_vote_mode",
        "both",
        {"both", "web_only", "telegram_only"},
    )
    return normalize_proposal_vote_mode(mode)


def is_web_proposal_voting_enabled():
    return get_proposal_vote_mode() in {"both", "web_only"}


def can_record_proposal_vote(source: str) -> bool:
    return can_record_proposal_vote_source(get_proposal_vote_mode(), source)


def log_proposal_vote_event(
    event, source, proposal_id, member_id, vote=None, reason_code=None, latency_ms=None
):
    app.logger.info(
        "event=%s source=%s mode=%s proposal_id=%s member_id=%s vote=%s reason_code=%s latency_ms=%s",
        event,
        source,
        get_proposal_vote_mode(),
        proposal_id,
        member_id,
        vote,
        reason_code,
        latency_ms,
    )


def record_proposal_vote(proposal_id, member_id, vote, source="web"):
    started_at = time.perf_counter()
    if not can_record_proposal_vote(source):
        log_proposal_vote_event(
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
def send_telegram_message(message, poll_id=None, options=None):
    client = TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID)
    if poll_id is not None and options is not None:
        return client.send_poll_message(message, poll_id, options)
    return client.send_message(message)


def send_telegram_admin_test_message(message, poll_id=None, options=None):
    client = TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID, "")
    if poll_id is not None and options is not None:
        return client.send_poll_message(message, poll_id, options)
    return client.send_message(message)


def sync_telegram_webhook(base_url: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_WEBHOOK_SECRET or not base_url:
        return False
    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}"
    client = TelegramClient(TELEGRAM_BOT_TOKEN, "", "")
    return client.set_webhook(webhook_url)


def sync_telegram_webhook_on_startup() -> str:
    """Synchronize a configured bot webhook after the database is ready.

    Returning a small status value lets startup distinguish an intentionally
    unconfigured integration from a Telegram API failure.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_WEBHOOK_SECRET:
        return "skipped"
    base_url = get_base_url().rstrip("/")
    if not base_url:
        app.logger.warning(
            "Telegram bot is configured but its Base URL is empty; webhook was not synchronized"
        )
        return "missing_base_url"
    if sync_telegram_webhook(base_url):
        app.logger.info("Telegram webhook synchronized")
        return "synced"
    app.logger.warning("Telegram webhook synchronization failed")
    return "failed"


def process_telegram_link_command(telegram_username, telegram_user_id, command_text):
    success, reason, linked_member_id = process_link_command(
        get_db=get_db,
        verify_and_migrate_password=verify_and_migrate_password,
        telegram_username=telegram_username,
        telegram_user_id=telegram_user_id,
        command_text=command_text,
    )
    if success and linked_member_id is not None:
        log_telegram_link_event(
            app.logger,
            event="telegram_link_updated",
            actor_id=linked_member_id,
            target_member_id=linked_member_id,
            source="telegram_command",
            reason_code="ok",
            status="success",
        )
    return success, reason


def process_telegram_vote_command(telegram_username, command_text, telegram_user_id=None):
    if not is_telegram_poll_voting_enabled():
        return False, "telegram_disabled"
    command = (command_text or "").strip()
    parts = command.split()
    if len(parts) not in (2, 3):
        return False, "invalid_format"

    command_name = parts[0].lower()
    if not (command_name == "/vote" or command_name.startswith("/vote@")):
        return False, "invalid_format"

    try:
        if len(parts) == 3:
            poll_id = int(parts[1])
            option_number = int(parts[2])
        else:
            option_number = int(parts[1])
            poll_id = None
    except ValueError:
        return False, "invalid_numbers"

    conn = get_db()
    c = conn.cursor()
    try:
        expired_poll_ids = close_expired_polls(conn)
        for expired_poll_id in expired_poll_ids:
            message = build_poll_results_message(conn, expired_poll_id)
            if message:
                send_telegram_message(message)
        require_linked = require_linked_telegram_for_votes()
        if require_linked:
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        else:
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(username) IN (?, ?) OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        member = c.fetchone()
        if member:
            voter_member_id = member["id"]
        elif telegram_user_id is not None:
            if require_linked:
                return False, "link_required"
            voter_member_id = -abs(int(telegram_user_id))
        else:
            return False, "unknown_member"

        if poll_id is None:
            c.execute("SELECT id, options_json, status FROM polls WHERE status = 'open' ORDER BY id DESC LIMIT 1")
            poll = c.fetchone()
            if not poll:
                return False, "poll_not_found"
            poll_id = poll["id"]
        else:
            c.execute("SELECT id, options_json, status FROM polls WHERE id = ?", (poll_id,))
            poll = c.fetchone()
        if not poll:
            return False, "poll_not_found"
        if poll["status"] != "open":
            return False, "poll_closed"

        try:
            options = json.loads(poll["options_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            options = []
        option_index = option_number - 1
        if option_index < 0 or option_index >= len(options):
            return False, "invalid_option"

        c.execute(
            "INSERT OR REPLACE INTO poll_votes (poll_id, member_id, option_index) VALUES (?, ?, ?)",
            (poll_id, voter_member_id, option_index),
        )
        conn.commit()
        return True, "ok"
    finally:
        conn.close()


def process_telegram_vote_callback(telegram_username, callback_data, telegram_user_id=None):
    data = (callback_data or "").strip()
    parts = data.split(":")

    if len(parts) == 3 and parts[0] == "pollvote":
        try:
            option_number = int(parts[2]) + 1
        except ValueError:
            return False, "invalid_numbers"
        return process_telegram_vote_command(telegram_username, f"/vote {parts[1]} {option_number}", telegram_user_id)

    if len(parts) == 3 and parts[0] == "pvote":
        proposal_id = parts[1]
        vote_token = parts[2]
        return process_telegram_proposal_vote_command(telegram_username, f"/pvote {proposal_id} {vote_token}", telegram_user_id)

    return False, "invalid_format"




def process_telegram_proposal_vote_command(telegram_username, command_text, telegram_user_id=None):
    command = (command_text or "").strip()
    parts = command.split()
    if len(parts) != 3:
        return False, "invalid_format"

    command_name = parts[0].lower()
    if not (command_name == "/pvote" or command_name.startswith("/pvote@")):
        return False, "invalid_format"

    try:
        proposal_id = int(parts[1])
    except ValueError:
        return False, "invalid_numbers"

    vote_raw = parts[2].strip().lower()
    if vote_raw in {"yes", "y", "in_favor", "favor", "for", "+"}:
        vote = "in_favor"
    elif vote_raw in {"no", "n", "against", "oppose", "-"}:
        vote = "against"
    else:
        return False, "invalid_vote"

    conn = get_db()
    c = conn.cursor()
    try:
        if require_linked_telegram_for_votes():
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        else:
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(username) IN (?, ?) OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        member = c.fetchone()
        if not member:
            return False, "link_required" if require_linked_telegram_for_votes() else "unknown_member"

        c.execute("SELECT id, status FROM proposals WHERE id = ?", (proposal_id,))
        proposal = c.fetchone()
        if not proposal:
            return False, "proposal_not_found"
        if proposal["status"] != "active":
            return False, "proposal_closed"

        ok = record_proposal_vote(proposal_id, member["id"], vote, source="telegram")
        if not ok:
            return False, "telegram_disabled"
        return True, "ok"
    finally:
        conn.close()

def process_proposal(proposal_id):
    conn = get_db()
    service = ProposalService(conn, TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID), get_base_url)
    result = service.process_proposal(proposal_id)
    conn.close()
    if result is True:
        check_over_budget_proposals()
    return result


def check_over_budget_proposals():
    conn = get_db()
    service = ProposalService(conn, TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID), get_base_url)
    service.check_over_budget_proposals()
    conn.close()


@app.route("/")
def index():
    from app.web.routes.auth_routes import index as index_impl

    return index_impl()


@app.route("/healthz")
def healthz():
    from app.web.routes.auth_routes import healthz as healthz_impl

    return healthz_impl()


@app.route("/telegram/webhook/<secret>", methods=["POST"])
@csrf.exempt
def telegram_webhook(secret):
    if not TELEGRAM_WEBHOOK_SECRET or not hmac.compare_digest(secret, TELEGRAM_WEBHOOK_SECRET):
        return {"ok": False}, 403

    payload = request.get_json(silent=True) or {}
    if not _telegram_update_deduplicator.accept(payload.get("update_id")):
        # Telegram retries webhook deliveries when acknowledgements are delayed.
        # Acknowledge duplicates without repeating votes, model calls, or MCP work.
        return {"ok": True}, 200
    callback_ctx = extract_callback_context(payload)
    if callback_ctx:
        def _load_open_poll_options(poll_id):
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT options_json FROM polls WHERE id = ? AND status = 'open'", (poll_id,))
            poll = c.fetchone()
            conn.close()
            if not poll:
                return None
            try:
                return json.loads(poll["options_json"] or "[]")
            except json.JSONDecodeError:
                return None

        result = dispatch_callback(
            callback_ctx,
            process_vote_callback=process_telegram_vote_callback,
            load_open_poll_options=_load_open_poll_options,
        )
        if TELEGRAM_BOT_TOKEN and result["kind"] == "showvote":
            client = TelegramClient(TELEGRAM_BOT_TOKEN, str(result["chat_id"]), "")
            updated = client.edit_message_with_vote_options(
                str(result["chat_id"]), result["message_id"], result["poll_id"], result["options"]
            )
            callback_text = "✅ Vote options shown" if updated else "❌ Couldn't show vote options"
            TelegramClient(TELEGRAM_BOT_TOKEN, "", "").answer_callback_query(result["callback_query_id"], callback_text)
        elif TELEGRAM_BOT_TOKEN:
            TelegramClient(TELEGRAM_BOT_TOKEN, "", "").answer_callback_query(callback_ctx["callback_query_id"], result["text"])
            if (
                result.get("kind") == "answer_callback"
                and not result.get("success", False)
                and result.get("reason") in {"link_required", "unknown_member"}
                and callback_ctx.get("telegram_user_id")
            ):
                TelegramClient(TELEGRAM_BOT_TOKEN, str(callback_ctx["telegram_user_id"]), "").send_message(result["text"])
        return {"ok": True}, 200

    message_ctx = extract_message_context(payload)
    chat_id = message_ctx["chat_id"]
    if not message_ctx["text"]:
        return {"ok": True}, 200

    # /link contains an application password. Remove the command message as soon
    # as possible (when Telegram permissions allow it), regardless of whether
    # credentials are valid. Linking itself is restricted to private chats below.
    if (
        classify_message_command(message_ctx["text"]) == "link"
        and TELEGRAM_BOT_TOKEN
        and chat_id
        and message_ctx.get("message_id") is not None
    ):
        TelegramClient(TELEGRAM_BOT_TOKEN, str(chat_id), "").delete_message(
            message_ctx["message_id"]
        )

    def _natural_language_reply(ctx, principal=None):
        if not telegram_agent.is_configured():
            return "Natural-language assistance is not configured. Use /help for available commands."
        principal = principal or get_telegram_principal(get_db, ctx["telegram_user_id"])
        if principal is None:
            return "❌ Link your account first with /link <app_username> <app_password>."

        def _notify_created_proposal(proposal_id, arguments):
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT username FROM members WHERE id = ?", (principal.member_id,)
                ).fetchone()
            finally:
                conn.close()
            creator = row["username"].split("@")[0] if row else "Unknown member"
            title = str(arguments.get("title") or "Untitled proposal")
            description = str(arguments.get("description") or "")
            amount = arguments.get("amount")
            proposal_url = str(arguments.get("url") or "")
            message = (
                f"*{title}*\n\n🆕 New proposal\nBy: {creator}\nAmount: €{amount}\n\n"
                f"{description[:200]}{'...' if len(description) > 200 else ''}\n\n"
                f"👉 {proposal_url or 'No link'}\n🔗 {get_base_url().rstrip('/')}/proposal/{proposal_id}"
            )
            client = TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID)
            if can_record_proposal_vote("telegram"):
                return client.send_proposal_vote_message(message, proposal_id)
            return client.send_message(message)

        try:
            return telegram_agent.answer(
                int(ctx["chat_id"]),
                ctx["text"],
                telegram_user_id=principal.telegram_user_id,
                actor_member_id=principal.member_id,
                is_admin=principal.is_admin,
                on_proposal_created=_notify_created_proposal,
            )
        except (requests.RequestException, RuntimeError, KeyError, IndexError, ValueError) as exc:
            app.logger.warning("Telegram natural-language request failed: %s", exc)
            return "❌ I couldn't contact the ManaVote assistant. Please try again later."

    # Telegram expects webhooks to acknowledge updates quickly. Ocabra may take
    # several seconds (and may perform multiple MCP rounds), so configured
    # natural-language work is completed outside the request thread.
    if (
        classify_message_command(message_ctx["text"]) == "other"
        and (
            is_natural_language_message(message_ctx, TELEGRAM_BOT_USERNAME)
            # A configured forum topic is a dedicated assistant conversation.
            # Telegram does not attach a mention entity to ordinary messages in
            # that topic, so requiring an @mention makes it appear unresponsive.
            or is_configured_forum_topic(
                message_ctx, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID
            )
        )
        and telegram_agent.is_configured()
        and TELEGRAM_BOT_TOKEN
        and chat_id
    ):
        # Refresh the allowlist for every update so link/unlink and admin-role
        # changes take effect without a process restart.
        principal = get_telegram_principal(get_db, message_ctx["telegram_user_id"])
        if principal is None:
            # Do not enqueue model work or reveal assistant behavior to senders
            # outside the database-backed allowlist. /help and /link remain
            # available through their deterministic command paths.
            return {"ok": True}, 200

        client = TelegramClient(
            TELEGRAM_BOT_TOKEN,
            str(chat_id),
            str(message_ctx.get("message_thread_id") or ""),
            message_ctx.get("message_id"),
        )
        thinking_message_id = client.send_message_with_id("🤔 Thinking…")

        def _answer_and_send(ctx):
            try:
                reply = _natural_language_reply(ctx, principal=principal)
                client.send_long_message(reply)
            finally:
                client.delete_message(thinking_message_id)

        future = _telegram_agent_executor.submit(_answer_and_send, dict(message_ctx))
        if future is None:
            app.logger.warning("Telegram assistant queue is full; dropping natural-language update")
            client.delete_message(thinking_message_id)
            client.send_message("⏳ The assistant is busy right now. Please try again shortly.")
        return {"ok": True}, 200

    result = dispatch_message(
        message_ctx,
        process_link_command=process_telegram_link_command,
        process_proposal_vote_command=process_telegram_proposal_vote_command,
        process_poll_vote_command=process_telegram_vote_command,
        process_natural_language=_natural_language_reply,
        process_reset=lambda ctx: telegram_agent.reset(
            int(ctx["chat_id"]), ctx["telegram_user_id"]
        ),
    )
    if TELEGRAM_BOT_TOKEN and chat_id and result["kind"] == "send_message":
        # Commands can arrive inside a forum topic just like natural-language
        # messages.  Keep their deterministic replies in that same topic rather
        # than silently posting them to the supergroup's General topic.
        TelegramClient(
            TELEGRAM_BOT_TOKEN,
            str(chat_id),
            str(message_ctx.get("message_thread_id") or ""),
            message_ctx.get("message_id"),
        ).send_message(result["text"])

    return {"ok": True}, 200


@app.route("/about")
def about():
    from app.web.routes.proposal_routes import about as about_impl

    return about_impl()


@app.route("/budget")
def budget():
    from app.web.routes.proposal_routes import budget as budget_impl

    return budget_impl()


@app.route("/settings")
@login_required
def settings_page():
    from app.web.routes.auth_routes import settings_page as settings_page_impl

    return settings_page_impl()


@app.route("/telegram-settings", methods=["GET", "POST"])
@login_required
def telegram_settings():
    from app.web.routes.auth_routes import telegram_settings as telegram_settings_impl

    return telegram_settings_impl()
@app.route("/register", methods=["GET", "POST"])
def register():
    from app.web.routes.auth_routes import register as register_impl

    return register_impl()


@app.route("/proposals")
@login_required
def proposals():
    from app.web.routes.proposal_routes import proposals as proposals_impl

    return proposals_impl()


@app.route("/admin/backups/<backup_type>/<filename>")
@admin_required
def download_backup_file(backup_type, filename):
    from app.web.routes.admin_routes import download_backup_file as download_backup_file_impl

    return download_backup_file_impl(backup_type, filename)


@login_required
def polls_page():
    from app.web.routes.poll_routes import polls_page as polls_page_impl

    return polls_page_impl()


@login_required
def check_overbudget():
    from app.web.routes.admin_routes import check_overbudget as check_overbudget_impl

    return check_overbudget_impl()


def migrate_password_if_needed(user_id, plaintext_password):
    """Migrate old SHA256 hash to werkzeug hash on login"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT password_hash FROM members WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False

    stored_hash = row[0]

    if stored_hash.startswith("pbkdf2:sha256:"):
        conn.close()
        return check_password_hash(stored_hash, plaintext_password)

    if stored_hash == hashlib.sha256(plaintext_password.encode()).hexdigest():
        new_hash = generate_password_hash(plaintext_password)
        c.execute(
            "UPDATE members SET password_hash = ? WHERE id = ?", (new_hash, user_id)
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


if __name__ == "__main__":
    ensure_db_ready()
    check_over_budget_proposals()
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=5000)
