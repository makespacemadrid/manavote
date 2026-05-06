"""Application package and factory."""

import logging
import os
import sqlite3

from .startup import run_startup_steps
from .web.app_setup import app as flask_app
from .web.routes.main_routes import *  # noqa: F401,F403


def create_app():
    """App factory entrypoint for WSGI servers and tests."""
    from .web.routes.main_routes import DB_PATH, UPLOAD_FOLDER

    app = flask_app
    try:
        run_startup_steps(app, DB_PATH, UPLOAD_FOLDER, os.getenv("FLASK_ENV", ""))
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise RuntimeError("Database initialization failed") from exc
    except ImportError as exc:
        logging.warning("Failed to initialize optional scheduler integrations: %s", exc)

    return app


app = create_app()
