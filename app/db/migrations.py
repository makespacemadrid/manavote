import sqlite3


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def add_column_if_missing(cursor, table_name, ddl):
    column_name = ddl.split()[0]
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _poll_votes_allows_multiple_options(cursor):
    """True once poll_votes' unique constraint covers option_index too, so a member
    can hold more than one row per poll (one per selected option)."""
    cursor.execute("PRAGMA index_list('poll_votes')")
    for _seq, index_name, is_unique, *_rest in cursor.fetchall():
        if not is_unique:
            continue
        cursor.execute(f"PRAGMA index_info({index_name})")
        columns = {info_row[2] for info_row in cursor.fetchall()}
        if columns == {"poll_id", "member_id", "option_index"}:
            return True
    return False


def _migrate_poll_votes_for_multi_select(cursor):
    """Existing databases have UNIQUE(poll_id, member_id) on poll_votes, which caps
    a member at one row per poll -- incompatible with multi-select polls. SQLite
    can't alter a UNIQUE constraint in place, so rebuild the table with the wider
    constraint, preserving every existing vote (each was already unique by
    (poll_id, member_id), so it stays unique under the new, looser constraint too)."""
    if _poll_votes_allows_multiple_options(cursor):
        return
    cursor.execute(
        """
        CREATE TABLE poll_votes_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            option_index INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(poll_id, member_id, option_index)
        )
        """
    )
    cursor.execute(
        "INSERT INTO poll_votes_new (id, poll_id, member_id, option_index, created_at) "
        "SELECT id, poll_id, member_id, option_index, created_at FROM poll_votes"
    )
    cursor.execute("DROP TABLE poll_votes")
    cursor.execute("ALTER TABLE poll_votes_new RENAME TO poll_votes")


def run_migrations(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coin_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        position INTEGER NOT NULL DEFAULT 0,
        pack_size INTEGER,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coin_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        inventory_delta INTEGER NOT NULL,
        coin_delta INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('consume', 'replenish', 'adjustment')),
        source TEXT NOT NULL CHECK (source IN ('web', 'qr', 'mcp', 'admin')),
        idempotency_key TEXT NOT NULL UNIQUE,
        note TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (item_id) REFERENCES coin_items(id),
        FOREIGN KEY (member_id) REFERENCES members(id),
        CHECK (inventory_delta <> 0 OR coin_delta <> 0),
        CHECK (kind = 'adjustment' OR inventory_delta = coin_delta)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_coin_movements_item_created ON coin_movements(item_id, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_coin_movements_member_created ON coin_movements(member_id, created_at DESC)")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coin_qr_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT NOT NULL UNIQUE,
        item_id INTEGER NOT NULL,
        action TEXT NOT NULL CHECK (action IN ('consume', 'replenish')),
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (item_id) REFERENCES coin_items(id),
        UNIQUE(item_id, action)
    )
    """)
    for position, name in enumerate(("Coke", "Coke Zero", "Other Can")):
        cursor.execute(
            "INSERT OR IGNORE INTO coin_items (name, position, pack_size) VALUES (?, ?, 12)",
            (name, position),
        )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        category TEXT NOT NULL,
        message TEXT NOT NULL,
        section TEXT,
        status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        resolved_by INTEGER
    )
    """)
    add_column_if_missing(cursor, "feedback", "section TEXT")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telegram_pending_actions (
        chat_id INTEGER NOT NULL,
        telegram_user_id INTEGER NOT NULL,
        tool_name TEXT NOT NULL,
        arguments_json TEXT NOT NULL,
        actor_member_id INTEGER,
        created_at REAL NOT NULL,
        schema_fingerprint TEXT,
        arguments_digest TEXT,
        PRIMARY KEY (chat_id, telegram_user_id)
    )
    """)
    add_column_if_missing(cursor, "telegram_pending_actions", "schema_fingerprint TEXT")
    add_column_if_missing(cursor, "telegram_pending_actions", "arguments_digest TEXT")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telegram_update_dedup (
        update_id INTEGER PRIMARY KEY,
        accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telegram_conversation_history (
        chat_id INTEGER NOT NULL,
        telegram_user_id INTEGER NOT NULL,
        messages_json TEXT NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (chat_id, telegram_user_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'open'
    )
    """)
    add_column_if_missing(cursor, "group_purchases", "deadline TEXT")
    add_column_if_missing(cursor, "group_purchases", "url TEXT")
    add_column_if_missing(cursor, "group_purchases", "image_filename TEXT")
    add_column_if_missing(cursor, "group_purchases", "payment_method TEXT")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_purchase_components (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_purchase_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        position INTEGER NOT NULL DEFAULT 0
    )
    """)
    add_column_if_missing(cursor, "group_purchase_components", "unit_price REAL NOT NULL DEFAULT 0")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_purchase_quantities (
        component_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (component_id, member_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_purchase_payments (
        group_purchase_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        received_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (group_purchase_id, member_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_purchase_shared_costs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_purchase_id INTEGER NOT NULL,
        label TEXT NOT NULL,
        amount REAL NOT NULL,
        position INTEGER NOT NULL DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        allow_multiple INTEGER NOT NULL DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS poll_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        option_index INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(poll_id, member_id, option_index)
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
    add_column_if_missing(cursor, "members", "last_linked_at TEXT")
    add_column_if_missing(cursor, "members", "last_unlinked_at TEXT")
    add_column_if_missing(cursor, "members", "oidc_sub TEXT")
    add_column_if_missing(cursor, "members", "email TEXT")
    add_column_if_missing(cursor, "members", "display_name TEXT")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_members_oidc_sub ON members(oidc_sub) WHERE oidc_sub IS NOT NULL")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_members_email_nocase "
        "ON members(email COLLATE NOCASE) WHERE email IS NOT NULL"
    )
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_members_telegram_user_id ON members(telegram_user_id) WHERE telegram_user_id IS NOT NULL")
    add_column_if_missing(cursor, "polls", "closes_at TEXT")
    add_column_if_missing(cursor, "polls", "allow_multiple INTEGER NOT NULL DEFAULT 0")
    _migrate_poll_votes_for_multi_select(cursor)
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
