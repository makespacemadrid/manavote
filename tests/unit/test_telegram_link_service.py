import sqlite3
import tempfile

from app.services.telegram_link_service import process_link_command, unlink_member_telegram


def _init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE members (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, telegram_username TEXT, telegram_user_id INTEGER)"
    )
    conn.execute(
        "INSERT INTO members (id, username, password_hash, telegram_username, telegram_user_id) VALUES (1, 'admin', 'hash', 'tg_user', 123)"
    )
    conn.commit()
    conn.close()


def test_unlink_member_telegram_clears_fields():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        _init_db(tmp.name)

        def get_db():
            conn = sqlite3.connect(tmp.name)
            conn.row_factory = sqlite3.Row
            return conn

        unlink_member_telegram(get_db, 1)
        conn = get_db()
        row = conn.execute("SELECT telegram_username, telegram_user_id FROM members WHERE id = 1").fetchone()
        conn.close()
        assert row["telegram_username"] is None
        assert row["telegram_user_id"] is None


def test_process_link_command_rejects_invalid_format():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        _init_db(tmp.name)

        def get_db():
            conn = sqlite3.connect(tmp.name)
            conn.row_factory = sqlite3.Row
            return conn

        ok, reason, member_id = process_link_command(
            get_db=get_db,
            verify_and_migrate_password=lambda *_: (True, None),
            telegram_username="user",
            telegram_user_id=9,
            command_text="/link only_username",
        )
        assert ok is False
        assert reason == "invalid_format"
        assert member_id is None


def test_process_link_command_links_member_on_valid_credentials():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        _init_db(tmp.name)

        def get_db():
            conn = sqlite3.connect(tmp.name)
            conn.row_factory = sqlite3.Row
            return conn

        ok, reason, member_id = process_link_command(
            get_db=get_db,
            verify_and_migrate_password=lambda *_: (True, None),
            telegram_username="new_tg",
            telegram_user_id=9001,
            command_text="/link admin good-pass",
        )
        assert ok is True
        assert reason == "ok"
        assert member_id == 1

        conn = get_db()
        row = conn.execute("SELECT telegram_username, telegram_user_id FROM members WHERE id = 1").fetchone()
        conn.close()
        assert row["telegram_username"] == "new_tg"
        assert row["telegram_user_id"] == 9001


def test_process_link_command_rejects_already_linked_user_id():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        _init_db(tmp.name)

        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO members (id, username, password_hash, telegram_username, telegram_user_id) VALUES (2, 'other', 'hash2', 'occupied', 9001)"
        )
        conn.commit()
        conn.close()

        def get_db():
            c = sqlite3.connect(tmp.name)
            c.row_factory = sqlite3.Row
            return c

        ok, reason, member_id = process_link_command(
            get_db=get_db,
            verify_and_migrate_password=lambda *_: (True, None),
            telegram_username="new_tg",
            telegram_user_id=9001,
            command_text="/link admin good-pass",
        )
        assert ok is False
        assert reason == "already_linked"
        assert member_id is None
