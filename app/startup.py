"""Startup orchestration helpers."""

import logging
import os
import sqlite3
import json
from datetime import datetime, timedelta

from .services.backup_service import start_scheduler
from .startup_policy import get_startup_runtime_policy
from .web.routes.main_routes import ensure_db_ready


def check_auto_backup(db_path, upload_dir=None):
    """Simple auto-backup check without APScheduler."""
    db_dir = os.path.dirname(db_path) or "."
    marker = os.path.join(db_dir, ".last_backup")
    now = datetime.now()

    if os.path.exists(marker):
        last = datetime.fromtimestamp(os.path.getmtime(marker))
        if now - last < timedelta(hours=24):
            return

    try:
        from .services.backup_service import backup_db, backup_uploads

        backup_db(db_path, keep_days=7)
        if upload_dir:
            backup_uploads(upload_dir, keep_days=7)
        with open(marker, "w") as f:
            f.write(str(now.timestamp()))
    except (OSError, sqlite3.Error, ValueError) as exc:
        logging.warning("Backup process failed: %s", exc)


def run_startup_steps(app, db_path, upload_folder, app_env=None):
    """Run startup steps in a deterministic order."""
    env = app_env or os.getenv("FLASK_ENV", "") or "development"
    degraded_reasons = []
    status = "ready"

    ensure_db_ready()

    runtime_policy = get_startup_runtime_policy(env)
    if runtime_policy["run_scheduler"]:
        try:
            start_scheduler(app, db_path, upload_folder)
        except OSError as exc:
            degraded_reasons.append("scheduler_start_failed")
            logging.warning("Failed to start scheduler: %s", exc)

    if runtime_policy["run_auto_backup"]:
        try:
            check_auto_backup(db_path, upload_folder)
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
