import sqlite3


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def add_column_if_missing(cursor, table_name, ddl):
    column_name = ddl.split()[0]
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def run_migrations(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS poll_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        option_index INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(poll_id, member_id)
    )
    """)
    add_column_if_missing(cursor, "settings", "url TEXT")
    add_column_if_missing(cursor, "proposals", "url TEXT")
    add_column_if_missing(cursor, "proposals", "image_filename TEXT")
    add_column_if_missing(cursor, "proposals", "purchased_at TEXT")
    add_column_if_missing(cursor, "proposals", "over_budget_at TEXT")
    add_column_if_missing(cursor, "activity_log", "created_by INTEGER")
    add_column_if_missing(cursor, "activity_log", "proposal_id INTEGER")
    add_column_if_missing(cursor, "polls", "status TEXT DEFAULT 'open'")
    add_column_if_missing(cursor, "members", "telegram_username TEXT")
    add_column_if_missing(cursor, "members", "telegram_user_id INTEGER")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_members_telegram_user_id ON members(telegram_user_id) WHERE telegram_user_id IS NOT NULL")
    add_column_if_missing(cursor, "polls", "closes_at TEXT")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('poll_vote_mode', 'both')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('proposal_vote_mode', 'both')")
    cursor.execute(
        """
        UPDATE activity_log
        SET proposal_id = (
            SELECT p.id
            FROM proposals p
            WHERE p.title = TRIM(REPLACE(REPLACE(activity_log.description, 'Approved: ', ''), 'Undo approval: ', ''))
            LIMIT 1
        )
        WHERE proposal_id IS NULL
          AND (
            description LIKE 'Approved: %'
            OR description LIKE 'Undo approval: %'
          )
        """
    )
    try:
        cursor.execute("UPDATE proposals SET basic_supplies = 0 WHERE basic_supplies = 1 AND amount > 20")
    except sqlite3.OperationalError:
        pass
