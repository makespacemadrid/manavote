import logging
import sqlite3
from datetime import datetime, timedelta

from app.services import poll_service


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

    closed_ids = poll_service.close_expired_polls(conn)

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

    message = poll_service.build_poll_results_message(conn, poll_id)

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

    message = poll_service.build_poll_results_message(conn, poll_id)

    assert "Broken payload" in message
    assert "No valid poll options were found." in message


def _settings(values):
    return lambda key, default=None: values.get(key, default)


def test_log_poll_vote_event_includes_current_mode(caplog):
    logger = logging.getLogger("test")

    with caplog.at_level("INFO", logger="test"):
        poll_service.log_poll_vote_event(
            logger,
            _settings({"poll_vote_mode": "web_only"}),
            event="poll_vote_rejected",
            source="telegram",
            poll_id=3,
            member_id=None,
            reason_code="channel_disabled",
        )

    assert [record.message for record in caplog.records] == [
        "event=poll_vote_rejected source=telegram mode=web_only poll_id=3 member_id=None reason_code=channel_disabled"
    ]


def test_log_poll_vote_event_defaults_poll_and_member_to_none(caplog):
    logger = logging.getLogger("test")

    with caplog.at_level("INFO", logger="test"):
        poll_service.log_poll_vote_event(
            logger,
            _settings({}),
            event="poll_vote_rejected",
            source="telegram",
            reason_code="channel_disabled",
        )

    assert [record.message for record in caplog.records] == [
        "event=poll_vote_rejected source=telegram mode=both poll_id=None member_id=None reason_code=channel_disabled"
    ]
