"""Application package and factory."""

import os
import logging
from datetime import datetime, timedelta
from .web.routes.main_routes import *  # noqa: F401,F403
from .web.routes.main_routes import app as flask_app


def create_app():
    """App factory entrypoint for WSGI servers and tests."""
    from .web.routes.main_routes import DB_PATH

    app = flask_app

    try:
        ensure_db_ready()
    except Exception as exc:
        logging.warning("DB initialization check failed: %s", exc)

    try:
        from .services.backup_service import start_scheduler
        start_scheduler(app, DB_PATH)
    except Exception as exc:
        logging.warning("Failed to start scheduler: %s", exc)

    try:
        check_auto_backup(DB_PATH)
    except Exception as exc:
        logging.warning("Auto backup check failed: %s", exc)

    return app


def check_auto_backup(db_path):
    """Simple auto-backup check without APScheduler."""
    db_dir = os.path.dirname(db_path) or "."
    marker = os.path.join(db_dir, ".last_backup")
    now = datetime.now()
    
    if os.path.exists(marker):
        last = datetime.fromtimestamp(os.path.getmtime(marker))
        if now - last < timedelta(hours=24):
            return
    
    try:
        from .services.backup_service import backup_db
        backup_db(db_path, keep_days=7)
        with open(marker, "w") as f:
            f.write(str(now.timestamp()))
    except Exception as exc:
        logging.warning("Backup process failed: %s", exc)


app = create_app()
