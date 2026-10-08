"""Schema/bootstrap ownership; callers supply runtime paths and policy."""

import os
import sqlite3
from werkzeug.security import generate_password_hash
from app.db.migrations import run_migrations


def initialize_database(db_path, *, testing, production, logger):
    conn = sqlite3.connect(db_path)
    try:
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
                if testing:
                    bootstrap_password = "test-admin-password"
                elif production:
                    raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD must be set before first startup in production")
                else:
                    bootstrap_password = "change-me-admin-password"
                    logger.warning(
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
    finally:
        conn.close()


def ensure_database_ready(connection_factory, initialize):
    conn = connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
        has_members = c.fetchone() is not None
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        has_settings = c.fetchone() is not None

        if not (has_members and has_settings):
            initialize()
            return

        # Always run migrations for existing databases so newly introduced
        # tables/columns (for example polls) are created before route handlers use them.
        run_migrations(c)
        conn.commit()
    finally:
        conn.close()
