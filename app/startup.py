"""Startup orchestration helpers."""

import logging
import os
import sqlite3
import json
from datetime import datetime, timedelta

from .services.backup_service import start_scheduler
from .startup_policy import get_startup_runtime_policy
from .web.routes.main_routes import ensure_db_ready, sync_telegram_webhook_on_startup


def check_telegram_group_configuration(logger=None, environ=None):
    """Warn when group message routing cannot identify this bot exactly."""
    logger = logger or logging.getLogger(__name__)
    environ = os.environ if environ is None else environ
    chat_id = environ.get("TELEGRAM_CHAT_ID", "").strip()
    thread_id = environ.get("TELEGRAM_THREAD_ID", "").strip()
    bot_username = environ.get("TELEGRAM_BOT_USERNAME", "").strip()

    # Telegram private-chat IDs are positive. Group and supergroup IDs are negative;
    # a configured thread also unambiguously identifies a forum supergroup.
    group_configured = chat_id.startswith("-") or bool(thread_id)
    if group_configured and not bot_username:
        logger.warning(
            "telegram_configuration_warning reason_code=%s "
            "TELEGRAM_BOT_USERNAME must be set for exact group mention matching",
            "missing_bot_username_for_group",
        )
        return "missing_bot_username_for_group"
    return None


def check_auto_backup(db_path, upload_dir=None, logger=None):
    """Simple auto-backup check without APScheduler."""
    logger = logger or logging.getLogger(__name__)
    db_dir = os.path.dirname(db_path) or "."
    marker = os.path.join(db_dir, ".last_backup")
    now = datetime.now()

    if os.path.exists(marker):
        last = datetime.fromtimestamp(os.path.getmtime(marker))
        if now - last < timedelta(hours=24):
            return

    from .services.backup_service import backup_db, backup_uploads
    from .web.routes.helpers.admin_audit_helpers import log_admin_backup_event

    backup_type = "db"
    try:
        backup_name, pruned_count = backup_db(db_path, keep_days=7)
        log_admin_backup_event(
            logger,
            event="startup_backup_created",
            actor_id=None,
            backup_type="db",
            file_name=backup_name,
            status="ok",
            pruned_count=pruned_count,
        )
        if upload_dir:
            backup_type = "images"
            backup_name, pruned_count = backup_uploads(upload_dir, keep_days=7)
            log_admin_backup_event(
                logger,
                event="startup_backup_created",
                actor_id=None,
                backup_type="images",
                file_name=backup_name,
                status="ok",
                pruned_count=pruned_count,
            )
        with open(marker, "w") as f:
            f.write(str(now.timestamp()))
    except (OSError, sqlite3.Error, ValueError) as exc:
        log_admin_backup_event(
            logger,
            event="startup_backup_failed",
            actor_id=None,
            backup_type=backup_type,
            reason_code="backup_exception",
            status="failed",
            error=str(exc),
        )
        logging.warning("Backup process failed: %s", exc)


def run_startup_steps(app, db_path, upload_folder, app_env=None):
    """Run startup steps in a deterministic order."""
    env = app_env or os.getenv("FLASK_ENV", "") or "development"
    degraded_reasons = []
    status = "ready"

    ensure_db_ready()

    check_telegram_group_configuration(logger=app.logger)
    telegram_status = sync_telegram_webhook_on_startup()
    if telegram_status not in {"skipped", "synced"}:
        degraded_reasons.append(f"telegram_webhook_{telegram_status}")

    runtime_policy = get_startup_runtime_policy(env)
    if runtime_policy["run_scheduler"]:
        try:
            start_scheduler(app, db_path, upload_folder)
        except OSError as exc:
            degraded_reasons.append("scheduler_start_failed")
            logging.warning("Failed to start scheduler: %s", exc)

    if runtime_policy["run_auto_backup"]:
        try:
            check_auto_backup(db_path, upload_folder, logger=app.logger)
        except (OSError, sqlite3.Error, ValueError) as exc:
            degraded_reasons.append("auto_backup_check_failed")
            logging.warning("Auto backup check failed: %s", exc)

    if degraded_reasons:
        status = "degraded"

    logging.info(
        "startup_summary %s",
        json.dumps(
            {
                "mode": env,
                "status": status,
                "degraded_reasons": degraded_reasons,
            },
            sort_keys=True,
        ),
    )
