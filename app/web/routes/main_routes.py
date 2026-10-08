import atexit
import logging
import os
import sqlite3
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
from app.db.connection import get_db as repo_get_db, set_db_path
from app.db.initialization import initialize_database, ensure_database_ready
from app.integrations.telegram_client import TelegramClient
from app.integrations.bounded_executor import BoundedExecutor
from app.integrations.member_admission import MemberAdmission
from app.integrations.assistant_jobs import AssistantJobs
from app.integrations import telegram_agent
from app.integrations.telegram_webhook import TelegramUpdateDeduplicator
from app.repositories.settings_repo import SettingsRepository
from app.repositories.budget_repo import BudgetRepository
from app.repositories.member_repo import MemberRepository
from app.repositories.vote_repo import VoteRepository
from app.services.auth_service import verify_and_migrate_password
from app.services.budget_service import calculate_min_backers
from app.services.proposal_service import ProposalService
from app.web.routes.helpers.admin_audit_helpers import log_admin_backup_event, log_telegram_link_event
from app.services import (
    poll_service,
    proposal_vote_recording_service,
    telegram_command_service,
    telegram_messaging_service,
    voting_mode_service,
)
from app.services.telegram_link_service import create_browser_link_token, process_link_command
from app.web.app_setup import app, BASE_DIR, is_production
from app.web.decorators import login_required, admin_required
from app.web.routes.helpers.main_helpers import (
    detect_image_type,
    format_datetime,
    truncate_username as helper_truncate_username,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import markdown
import warnings


telegram_agent.ModelLimits.from_env()  # Validate assistant request budgets at startup.
_telegram_member_admission = MemberAdmission(os.getenv("TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER", "1"))
_telegram_jobs = AssistantJobs()
_telegram_agent_executor = BoundedExecutor(
    max_workers=4,
    max_pending=32,
    thread_name_prefix="telegram-agent",
)
atexit.register(_telegram_agent_executor.shutdown)
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


@app.template_filter("currency")
def currency_filter(value):
    """Format a numeric amount consistently with grouping and two decimals."""
    return f"{float(value or 0):,.2f}"


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
    return initialize_database(DB_PATH, testing=app.config.get("TESTING"),
                               production=is_production, logger=app.logger)


def ensure_db_ready():
    return ensure_database_ready(repo_get_db, init_db)


def close_expired_polls(conn):
    return poll_service.close_expired_polls(conn)


def build_poll_results_message(conn, poll_id):
    return poll_service.build_poll_results_message(conn, poll_id)


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
    try:
        return BudgetRepository(conn).current_budget()
    finally:
        conn.close()


def get_member_count():
    conn = get_db()
    try:
        return MemberRepository(conn).count()
    finally:
        conn.close()


def get_thresholds():
    conn = get_db()
    thresholds = SettingsRepository(conn).get_thresholds()
    conn.close()
    return thresholds




def get_vote_counts(cursor, proposal_id):
    return VoteRepository(cursor.connection).get_counts(proposal_id)


def is_registration_enabled():
    return voting_mode_service.is_registration_enabled(get_setting_value)


def get_poll_vote_mode():
    return voting_mode_service.get_poll_vote_mode(get_setting_value)


def is_web_poll_voting_enabled():
    return voting_mode_service.is_web_poll_voting_enabled(get_setting_value)


def is_telegram_poll_voting_enabled():
    return voting_mode_service.is_telegram_poll_voting_enabled(get_setting_value)


def require_linked_telegram_for_votes():
    return voting_mode_service.require_linked_telegram_for_votes(get_setting_value)


def get_proposal_vote_mode():
    return voting_mode_service.get_proposal_vote_mode(get_setting_value)


def is_web_proposal_voting_enabled():
    return voting_mode_service.is_web_proposal_voting_enabled(get_setting_value)


def can_record_proposal_vote(source: str) -> bool:
    return voting_mode_service.can_record_proposal_vote(get_setting_value, source)


def log_proposal_vote_event(
    event, source, proposal_id, member_id, vote=None, reason_code=None, latency_ms=None
):
    proposal_vote_recording_service.log_proposal_vote_event(
        app.logger, get_setting_value, event, source, proposal_id, member_id, vote, reason_code, latency_ms
    )


def record_proposal_vote(proposal_id, member_id, vote, source="web"):
    return proposal_vote_recording_service.record_proposal_vote(
        get_db, get_setting_value, process_proposal, app.logger, proposal_id, member_id, vote, source
    )


def send_telegram_message(message, poll_id=None, options=None):
    return telegram_messaging_service.send_telegram_message(
        TelegramClient, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID, message, poll_id, options
    )


def send_telegram_admin_test_message(message, poll_id=None, options=None):
    return telegram_messaging_service.send_telegram_admin_test_message(
        TelegramClient, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID, message, poll_id, options
    )


def sync_telegram_webhook(base_url: str) -> bool:
    return telegram_messaging_service.sync_telegram_webhook(
        TelegramClient, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, base_url
    )


def sync_telegram_webhook_on_startup() -> str:
    return telegram_messaging_service.sync_telegram_webhook_on_startup(
        TelegramClient, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, get_base_url, app.logger
    )


def process_telegram_link_command(telegram_username, telegram_user_id, command_text):
    success, reason, linked_member_id = process_link_command(
        get_db=get_db,
        verify_and_migrate_password=verify_and_migrate_password,
        telegram_username=telegram_username,
        telegram_user_id=telegram_user_id,
        command_text=command_text,
    )
    if reason == "invalid_format" and len((command_text or "").strip().split()) == 1:
        token = create_browser_link_token(app.secret_key, telegram_username, telegram_user_id)
        return False, f"browser_link:{get_base_url().rstrip('/')}/telegram/link/{token}"
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
    return telegram_command_service.process_telegram_vote_command(
        get_db,
        get_setting_value,
        send_telegram_message,
        app.logger,
        telegram_username,
        command_text,
        telegram_user_id,
    )


def process_telegram_vote_callback(telegram_username, callback_data, telegram_user_id=None):
    return telegram_command_service.process_telegram_vote_callback(
        get_db,
        get_setting_value,
        send_telegram_message,
        record_proposal_vote,
        app.logger,
        telegram_username,
        callback_data,
        telegram_user_id,
    )


def process_telegram_proposal_vote_command(telegram_username, command_text, telegram_user_id=None):
    return telegram_command_service.process_telegram_proposal_vote_command(
        get_db,
        get_setting_value,
        record_proposal_vote,
        app.logger,
        telegram_username,
        command_text,
        telegram_user_id,
    )

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


if __name__ == "__main__":
    ensure_db_ready()
    check_over_budget_proposals()
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=5000)
