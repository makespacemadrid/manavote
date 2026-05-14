import sqlite3
from datetime import datetime, timedelta

from app.web.routes import main_routes


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("CREATE TABLE polls (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, options_json TEXT, status TEXT, closes_at TEXT)")
    c.execute("CREATE TABLE poll_votes (poll_id INTEGER, member_id INTEGER, option_index INTEGER)")
    conn.commit()
    return conn


def test_close_expired_polls_only_closes_expired_open_polls():
    conn = _make_conn()
    c = conn.cursor()
    past = (datetime.now() - timedelta(minutes=5)).isoformat()
    future = (datetime.now() + timedelta(minutes=5)).isoformat()
    c.execute("INSERT INTO polls (question, options_json, status, closes_at) VALUES ('old', '[\"a\",\"b\"]', 'open', ?)", (past,))
    c.execute("INSERT INTO polls (question, options_json, status, closes_at) VALUES ('new', '[\"a\",\"b\"]', 'open', ?)", (future,))
    c.execute("INSERT INTO polls (question, options_json, status, closes_at) VALUES ('closed', '[\"a\",\"b\"]', 'closed', ?)", (past,))
    conn.commit()

    closed_ids = main_routes.close_expired_polls(conn)

    assert len(closed_ids) == 1
    c.execute("SELECT status FROM polls WHERE question = 'old'")
    assert c.fetchone()["status"] == "closed"
    c.execute("SELECT status FROM polls WHERE question = 'new'")
    assert c.fetchone()["status"] == "open"


def test_build_poll_results_message_contains_graph_and_totals():
    conn = _make_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO polls (question, options_json, status, closes_at) VALUES ('A new lamp', '[\"Yes\",\"No\"]', 'closed', ?)",
        (datetime.now().isoformat(),),
    )
    poll_id = c.lastrowid
    c.executemany(
        "INSERT INTO poll_votes (poll_id, member_id, option_index) VALUES (?, ?, ?)",
        [(poll_id, 1, 0), (poll_id, 2, 0), (poll_id, 3, 1)],
    )
    conn.commit()

    message = main_routes.build_poll_results_message(conn, poll_id)

    assert "A new lamp" in message
    assert "Total votes: *3*" in message
    assert "vote(s)" in message
    assert "█" in message


def test_build_poll_results_message_handles_invalid_options_payload():
    conn = _make_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO polls (question, options_json, status, closes_at) VALUES ('Broken payload', 'not-json', 'closed', ?)",
        (datetime.now().isoformat(),),
    )
    poll_id = c.lastrowid
    conn.commit()

    message = main_routes.build_poll_results_message(conn, poll_id)

    assert "Broken payload" in message
    assert "No valid poll options were found." in message
