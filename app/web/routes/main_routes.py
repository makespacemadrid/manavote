import os
import sqlite3
import hashlib
import secrets
import hmac
import logging
from datetime import datetime, date, timedelta, timezone
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
from app.integrations.telegram_webhook import (
    dispatch_callback,
    dispatch_message,
    extract_callback_context,
    extract_message_context,
)
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_repo import VoteRepository
from app.services.auth_service import verify_and_migrate_password
from app.services.budget_service import calculate_min_backers
from app.services.proposal_service import ProposalService
from app.web.routes.helpers.admin_audit_helpers import log_admin_backup_event
from app.services.proposal_vote_service import can_record_proposal_vote_source, normalize_proposal_vote_mode
from app.services.settings_service import get_enum_setting
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


def process_telegram_link_command(telegram_username, telegram_user_id, command_text):
    command = (command_text or "").strip()
    parts = command.split(maxsplit=2)
    if len(parts) != 3:
        return False, "invalid_format"
    if not (telegram_username or "").strip():
        return False, "missing_public_username"

    app_username = parts[1].strip()
    password = parts[2]
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, password_hash FROM members WHERE lower(username) = lower(?)", (app_username,))
        member = c.fetchone()
        if not member:
            return False, "unknown_member"
        ok, new_hash = verify_and_migrate_password(member["password_hash"], password)
        if not ok:
            return False, "invalid_credentials"
        if new_hash:
            c.execute("UPDATE members SET password_hash = ? WHERE id = ?", (new_hash, member["id"]))

        c.execute("SELECT id FROM members WHERE telegram_user_id = ? AND id != ?", (telegram_user_id, member["id"]))
        linked = c.fetchone()
        if linked:
            return False, "already_linked"

        c.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            (telegram_username, int(telegram_user_id), member["id"]),
        )
        conn.commit()
        return True, "ok"
    finally:
        conn.close()


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

    result = dispatch_message(
        message_ctx,
        process_link_command=process_telegram_link_command,
        process_proposal_vote_command=process_telegram_proposal_vote_command,
        process_poll_vote_command=process_telegram_vote_command,
    )
    if TELEGRAM_BOT_TOKEN and chat_id and result["kind"] == "send_message":
        TelegramClient(TELEGRAM_BOT_TOKEN, str(chat_id), "").send_message(result["text"])

    return {"ok": True}, 200


@app.route("/about")
def about():
    from app.web.routes.proposal_routes import about as about_impl

    return about_impl()


@app.route("/calendar")
def calendar():
    from app.web.routes.proposal_routes import calendar as calendar_impl

    return calendar_impl()


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


@app.route("/dashboard")
@login_required
def dashboard():
    from flask import make_response

    conn = get_db()
    c = conn.cursor()

    filter_type = request.args.get("filter", "active")

    if filter_type == "basic":
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.basic_supplies = 1 ORDER BY p.created_at DESC"
        )
    elif filter_type in ("active", "approved", "over_budget"):
        c.execute(
            "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.status = ? ORDER BY p.created_at DESC",
            (filter_type,),
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
        "dashboard.html",
        proposals=proposals,
        filter=filter_type,
        total_count=total_count,
        current_budget=current_budget,
        budget_history=budget_history,
        member_count=member_count,
        active_proposals_sum=active_proposals_sum,
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


@login_required
def new_proposal():
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
        message = f"🆕 *New Proposal!*\n\n*{title}*\nBy: {creator.split('@')[0]}\nAmount: €{amount}{deadline_line}\n\n{description[:200]}{'...' if len(description) > 200 else ''}\n\n👉 {url if url else 'No link'}\n🔗 {base_url}/proposal/{proposal_id}"
        if can_record_proposal_vote("telegram"):
            TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID).send_proposal_vote_message(message, proposal_id)
        else:
            send_telegram_message(message)

        flash("Proposal created!", "success")
        return redirect(url_for("dashboard"))

    current_budget = get_current_budget()
    thresholds = get_thresholds()
    return render_template(
        "new_proposal.html",
        current_budget=current_budget,
        thresholds=thresholds,
        session_lang=session.get("lang", "en"),
    )


@login_required
def proposal_detail(proposal_id):
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
        return redirect(url_for("dashboard"))

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


@login_required
def edit_comment(comment_id):
    if not session.get("is_admin"):
        flash("Admin access required", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = c.fetchone()

    if not comment:
        conn.close()
        flash("Comment not found", "error")
        return redirect(url_for("dashboard"))

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
        backups=backups,
        polls=polls,
    )


@login_required
def delete_comment(comment_id):
    if not session.get("is_admin"):
        flash("Admin access required", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = c.fetchone()

    if not comment:
        conn.close()
        flash("Comment not found", "error")
        return redirect(url_for("dashboard"))

    proposal_id = comment["proposal_id"]
    c.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()

    flash("Comment deleted!", "success")
    return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))


@login_required
def delete_proposal(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

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
    return redirect(url_for("dashboard"))


@login_required
def edit_proposal(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    if proposal["created_by"] != session["member_id"] and not session.get("is_admin"):
        conn.close()
        flash("You can only edit your own proposals", "error")
        return redirect(url_for("dashboard"))

    if proposal["status"] != "active":
        conn.close()
        flash("Cannot edit processed proposals", "error")
        return redirect(url_for("dashboard"))

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
        backups=backups,
        polls=polls,
    )


@login_required
def quick_vote(proposal_id):
    if not can_record_proposal_vote("web"):
        flash("Web voting is disabled by admin", "error")
        return redirect(url_for("dashboard"))

    vote = request.form.get("vote")
    record_proposal_vote(proposal_id, session["member_id"], vote, source="web")
    flash("Vote recorded!", "success")
    return redirect(url_for("dashboard"))


@login_required
def withdraw_vote(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
    status = c.fetchone()

    if status and status["status"] != "active":
        conn.close()
        flash("Cannot withdraw vote on processed proposals", "error")
        return redirect(url_for("dashboard"))

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
    return redirect(url_for("dashboard"))


@admin_required
def undo_approve(proposal_id):
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
    return redirect(url_for("dashboard"))


@login_required
def mark_purchased(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

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


@login_required
def unmark_purchased(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    if proposal["status"] != "approved":
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    c.execute(
        "UPDATE proposals SET purchased_at = NULL WHERE id = ?",
        (proposal_id,),
    )
    conn.commit()
    conn.close()

    flash("Purchase status removed", "success")
    return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))


@admin_required
def admin():
    ensure_db_ready()
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_member":
            username = request.form["username"]
            password = request.form["password"]
            is_admin = 1 if request.form.get("is_admin") else 0
            password_hash = generate_password_hash(password)

            try:
                c.execute(
                    "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, ?)",
                    (username, password_hash, is_admin),
                )
                conn.commit()
                flash(f"Member {username} added!", "success")
            except sqlite3.IntegrityError:
                flash("Username already exists", "error")

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
            c.execute(
                "UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE id = ?",
                (member_id,),
            )
            conn.commit()
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
            if amount <= 0:
                flash("Amount must be positive", "error")
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
                check_over_budget_proposals()
                flash(
                    f"Added €{amount} to budget! New balance: €{get_current_budget()}",
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
            base_url = request.form.get("base_url", "").rstrip("/")
            if base_url:
                c.execute(
                    "INSERT INTO settings (key, value) VALUES ('url', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (base_url,),
                )
            conn.commit()
            synced = sync_telegram_webhook(base_url) if base_url else False
            if synced:
                flash("Base URL updated and Telegram webhook synced!", "success")
            else:
                flash("Base URL updated!", "success")

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
            options = [line.strip() for line in raw_options.splitlines() if line.strip()]
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
            else:
                c.execute(
                    "INSERT INTO polls (question, options_json, created_by, status) VALUES (?, ?, ?, 'open')",
                    (question, json.dumps(options), session["member_id"]),
                )
                poll_id = c.lastrowid
                conn.commit()
                flash("Poll created!", "success")


        elif action == "close_poll":
            poll_id = request.form.get("poll_id", type=int)
            c.execute(
                "UPDATE polls SET status = 'closed', closes_at = ? WHERE id = ?",
                (datetime.now().isoformat(), poll_id),
            )
            conn.commit()
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
                lines = [f"📊 *New Poll*", f"", f"*{poll['question']}*", ""]
                for idx, option in enumerate(options, 1):
                    lines.append(f"{idx}. {option}")
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

        elif action == "backup_db":
            try:
                from app.services.backup_service import backup_db

                backup_name, pruned_count = backup_db(DB_PATH, keep_days=7)
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
            except Exception as exc:
                log_admin_backup_event(
                    app.logger,
                    event="admin_backup_failed",
                    actor_id=session.get("member_id"),
                    backup_type="db",
                    reason_code="backup_exception",
                    status="failed",
                    error=str(exc),
                )
                flash(f"Backup failed: {exc}", "error")
        elif action == "backup_images":
            try:
                from app.services.backup_service import backup_uploads

                backup_name, pruned_count = backup_uploads(app.config["UPLOAD_FOLDER"], keep_days=7)
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
            except Exception as exc:
                log_admin_backup_event(
                    app.logger,
                    event="admin_backup_failed",
                    actor_id=session.get("member_id"),
                    backup_type="images",
                    reason_code="backup_exception",
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
    except Exception:
        polls = []

    c.execute("SELECT value FROM settings WHERE key = 'timezone'")
    tz_row = c.fetchone()
    current_timezone = tz_row["value"] if tz_row else "Europe/Madrid"

    requested_tab = request.values.get("tab", "all")
    allowed_tabs = {"all", "members", "budget", "polls", "settings"}
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
        active_admin_tab=active_admin_tab,
    )


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
