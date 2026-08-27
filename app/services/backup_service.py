import os
import shutil
import logging
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
BACKUP_ROOT = os.path.join(REPO_ROOT, "backups")


def backup_db(db_path, keep_days=7, backup_root=BACKUP_ROOT):
    """Create timestamped backup and prune old backups."""
    os.makedirs(backup_root, exist_ok=True)
    base_name = os.path.basename(db_path).replace(".db", "")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{base_name}_{timestamp}.db"
    backup_path = os.path.join(backup_root, backup_name)

    shutil.copy2(db_path, backup_path)

    cutoff = datetime.now() - timedelta(days=keep_days)
    count = 0
    for filename in os.listdir(backup_root):
        if filename.startswith(base_name + "_") and filename.endswith(".db"):
            filepath = os.path.join(backup_root, filename)
            if datetime.fromtimestamp(os.path.getmtime(filepath)) < cutoff:
                os.remove(filepath)
                count += 1

    return backup_name, count


def backup_uploads(upload_dir, keep_days=7, backup_root=BACKUP_ROOT):
    """Create timestamped uploads snapshot and prune old snapshots."""
    os.makedirs(backup_root, exist_ok=True)
    backup_dir = backup_root
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"uploads_{timestamp}.zip"
    archive_base = os.path.join(backup_dir, backup_name[:-4])

    shutil.make_archive(archive_base, "zip", upload_dir)

    cutoff = datetime.now() - timedelta(days=keep_days)
    count = 0
    for filename in os.listdir(backup_dir):
        if filename.startswith("uploads_") and filename.endswith(".zip"):
            filepath = os.path.join(backup_dir, filename)
            if datetime.fromtimestamp(os.path.getmtime(filepath)) < cutoff:
                os.remove(filepath)
                count += 1

    return backup_name, count


def _scheduled_backup_job(app, backup_type, backup_fn, *args):
    """Run a scheduled backup and emit a structured lifecycle event.

    APScheduler's own executor only logs uncaught exceptions to the generic
    logger, so this wrapper guarantees every scheduled run leaves a
    structured `scheduled_backup_created`/`scheduled_backup_failed` event
    even when the backup itself raises.
    """
    from app.web.routes.helpers.admin_audit_helpers import log_admin_backup_event

    try:
        backup_name, pruned_count = backup_fn(*args, keep_days=7)
    except Exception as exc:
        log_admin_backup_event(
            app.logger,
            event="scheduled_backup_failed",
            actor_id=None,
            backup_type=backup_type,
            reason_code="backup_exception",
            status="failed",
            error=str(exc),
        )
        return
    log_admin_backup_event(
        app.logger,
        event="scheduled_backup_created",
        actor_id=None,
        backup_type=backup_type,
        file_name=backup_name,
        status="ok",
        pruned_count=pruned_count,
    )


def start_scheduler(app, db_path, upload_dir=None):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "APScheduler unavailable (%s); automatic backups disabled. "
            "Install with `pip install APScheduler` and verify the same Python environment is used at runtime.",
            exc,
        )
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _scheduled_backup_job,
        "interval",
        hours=24,
        args=[app, "db", backup_db, db_path],
        id="daily_backup",
        replace_existing=True,
    )
    if upload_dir:
        scheduler.add_job(
            _scheduled_backup_job,
            "interval",
            hours=24,
            args=[app, "images", backup_uploads, upload_dir],
            id="daily_uploads_backup",
            replace_existing=True,
        )
    try:
        scheduler.start()
    except Exception as exc:
        logging.getLogger(__name__).warning("APScheduler failed to start: %s", exc)
        return None
    app.scheduler = scheduler
    return scheduler
