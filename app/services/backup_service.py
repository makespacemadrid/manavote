import os
import shutil
import logging
from datetime import datetime, timedelta


def backup_db(db_path, keep_days=7):
    """Create timestamped backup and prune old backups."""
    directory = os.path.dirname(db_path) or "."
    base_name = os.path.basename(db_path).replace(".db", "")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{base_name}_{timestamp}.db"
    backup_path = os.path.join(directory, backup_name)

    shutil.copy2(db_path, backup_path)

    cutoff = datetime.now() - timedelta(days=keep_days)
    count = 0
    for filename in os.listdir(directory):
        if filename.startswith(base_name + "_") and filename.endswith(".db"):
            filepath = os.path.join(directory, filename)
            if datetime.fromtimestamp(os.path.getmtime(filepath)) < cutoff:
                os.remove(filepath)
                count += 1

    return backup_name, count


def start_scheduler(app, db_path):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logging.getLogger(__name__).warning("APScheduler not installed; automatic backups disabled")
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        backup_db,
        "interval",
        hours=24,
        args=[db_path, 7],
        id="daily_backup",
        replace_existing=True,
    )
    scheduler.start()
    app.scheduler = scheduler
    return scheduler
