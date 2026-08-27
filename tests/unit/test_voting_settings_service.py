import sqlite3

from app.services import voting_settings_service


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


def _all_settings(conn):
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings").fetchall()}


def test_apply_voting_settings_writes_only_provided_keys():
    conn = _make_conn()

    voting_settings_service.apply_voting_settings(conn, poll_vote_mode="web_only")

    assert _all_settings(conn) == {"poll_vote_mode": "web_only"}


def test_apply_voting_settings_writes_all_three_when_provided():
    conn = _make_conn()

    voting_settings_service.apply_voting_settings(
        conn,
        poll_vote_mode="telegram_only",
        proposal_vote_mode="both",
        telegram_require_linked_vote=True,
    )

    assert _all_settings(conn) == {
        "poll_vote_mode": "telegram_only",
        "proposal_vote_mode": "both",
        "telegram_require_linked_vote": "true",
    }


def test_apply_voting_settings_stores_false_as_string():
    conn = _make_conn()

    voting_settings_service.apply_voting_settings(conn, telegram_require_linked_vote=False)

    assert _all_settings(conn) == {"telegram_require_linked_vote": "false"}


def test_apply_voting_settings_overwrites_existing_value():
    conn = _make_conn()
    conn.execute("INSERT INTO settings (key, value) VALUES ('poll_vote_mode', 'both')")
    conn.commit()

    voting_settings_service.apply_voting_settings(conn, poll_vote_mode="web_only")

    assert _all_settings(conn) == {"poll_vote_mode": "web_only"}


def test_valid_vote_modes_contains_expected_values():
    assert voting_settings_service.VALID_VOTE_MODES == {"both", "web_only", "telegram_only"}
