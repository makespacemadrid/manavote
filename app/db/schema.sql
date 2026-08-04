CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    telegram_username TEXT,
    telegram_user_id INTEGER,
    oidc_sub TEXT UNIQUE,
    email TEXT,
    display_name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_members_email_nocase
    ON members(email COLLATE NOCASE) WHERE email IS NOT NULL;
CREATE TABLE IF NOT EXISTS proposals (
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
    over_budget_at TEXT,
    purchased_at TEXT,
    basic_supplies INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    vote TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(proposal_id, member_id)
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    description TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    options_json TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'open',
    closes_at TEXT
);
CREATE TABLE IF NOT EXISTS poll_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    option_index INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(poll_id, member_id)
);
CREATE TABLE IF NOT EXISTS group_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'open',
    deadline TEXT,
    url TEXT,
    image_filename TEXT,
    payment_method TEXT
);
CREATE TABLE IF NOT EXISTS group_purchase_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_purchase_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    unit_price REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS group_purchase_quantities (
    component_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (component_id, member_id)
);
CREATE TABLE IF NOT EXISTS group_purchase_payments (
    group_purchase_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    received_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (group_purchase_id, member_id)
);
CREATE TABLE IF NOT EXISTS group_purchase_shared_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_purchase_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    amount REAL NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
