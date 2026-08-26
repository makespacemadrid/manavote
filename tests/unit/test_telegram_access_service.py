import sqlite3

from app.services.telegram_access_service import (
    get_telegram_principal,
    load_telegram_principals,
)


def _database(tmp_path):
    path = tmp_path / "telegram-access.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE members (id INTEGER PRIMARY KEY, telegram_user_id INTEGER, is_admin INTEGER)"
    )
    conn.executemany(
        "INSERT INTO members (id, telegram_user_id, is_admin) VALUES (?, ?, ?)",
        [(1, 101, 0), (2, 202, 1), (3, None, 1)],
    )
    conn.commit()
    conn.close()

    def get_db():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    return get_db, path


def test_allowlist_is_loaded_from_linked_member_telegram_ids(tmp_path):
    get_db, _path = _database(tmp_path)

    principals = load_telegram_principals(get_db)

    assert set(principals) == {101, 202}
    assert principals[101].member_id == 1
    assert principals[101].is_admin is False
    assert principals[202].is_admin is True


def test_principal_lookup_rejects_missing_or_invalid_ids(tmp_path):
    get_db, _path = _database(tmp_path)

    assert get_telegram_principal(get_db, 999) is None
    assert get_telegram_principal(get_db, None) is None
    assert get_telegram_principal(get_db, "not-an-id") is None


def test_allowlist_refreshes_after_database_link_change(tmp_path):
    get_db, path = _database(tmp_path)
    assert get_telegram_principal(get_db, 303) is None

    conn = sqlite3.connect(path)
    conn.execute("UPDATE members SET telegram_user_id = 303 WHERE id = 3")
    conn.commit()
    conn.close()

    principal = get_telegram_principal(get_db, 303)
    assert principal is not None
    assert principal.member_id == 3
    assert principal.is_admin is True
