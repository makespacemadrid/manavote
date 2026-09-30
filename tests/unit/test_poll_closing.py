import logging
import sqlite3
from datetime import datetime, timedelta

from app.services import poll_service


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "CREATE TABLE polls (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, options_json TEXT, "
        "status TEXT, closes_at TEXT, allow_multiple INTEGER NOT NULL DEFAULT 0)"
    )
    c.execute(
        "CREATE TABLE poll_votes (poll_id INTEGER, member_id INTEGER, option_index INTEGER, "
        "UNIQUE(poll_id, member_id, option_index))"
    )
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


def test_build_poll_announcement_message_includes_question_and_numbered_options():
    message = poll_service.build_poll_announcement_message("Where should we meet?", ["Office", "Cafe"])

    assert "Where should we meet?" in message
    assert "1. Office" in message
    assert "2. Cafe" in message
    assert "Tap a button below to vote." in message
    assert "Closes" not in message


def test_build_poll_announcement_message_includes_closing_time_when_given():
    message = poll_service.build_poll_announcement_message(
        "Where should we meet?", ["Office", "Cafe"], closes_at="2026-12-01T10:00:00"
    )

    assert "⏰ Closes: 2026-12-01 10:00" in message


def test_build_poll_announcement_message_falls_back_to_raw_closes_at_on_bad_format():
    message = poll_service.build_poll_announcement_message(
        "Where should we meet?", ["Office", "Cafe"], closes_at="not-a-date"
    )

    assert "⏰ Closes: not-a-date" in message


def test_build_poll_announcement_message_notes_multi_select():
    message = poll_service.build_poll_announcement_message(
        "Where should we meet?", ["Office", "Cafe"], allow_multiple=True
    )

    assert "You may select more than one option. Tap a button below to vote." in message


def test_record_poll_vote_single_select_replaces_prior_selection():
    conn = _make_conn()
    c = conn.cursor()
    c.execute("INSERT INTO polls (question, options_json, status) VALUES ('Q', '[\"a\",\"b\",\"c\"]', 'open')")
    poll_id = c.lastrowid
    conn.commit()

    poll_service.record_poll_vote(conn, poll_id, member_id=1, option_index=0, allow_multiple=False)
    poll_service.record_poll_vote(conn, poll_id, member_id=1, option_index=2, allow_multiple=False)

    c.execute("SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = ?", (poll_id, 1))
    rows = c.fetchall()
    assert [r["option_index"] for r in rows] == [2]


def test_record_poll_vote_multi_select_toggles_independently():
    conn = _make_conn()
    c = conn.cursor()
    c.execute("INSERT INTO polls (question, options_json, status) VALUES ('Q', '[\"a\",\"b\",\"c\"]', 'open')")
    poll_id = c.lastrowid
    conn.commit()

    assert poll_service.record_poll_vote(conn, poll_id, member_id=1, option_index=0, allow_multiple=True) is True
    assert poll_service.record_poll_vote(conn, poll_id, member_id=1, option_index=2, allow_multiple=True) is True
    c.execute(
        "SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = ? ORDER BY option_index",
        (poll_id, 1),
    )
    assert [r["option_index"] for r in c.fetchall()] == [0, 2]

    assert poll_service.record_poll_vote(conn, poll_id, member_id=1, option_index=0, allow_multiple=True) is False
    c.execute(
        "SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = ? ORDER BY option_index",
        (poll_id, 1),
    )
    assert [r["option_index"] for r in c.fetchall()] == [2]


def test_build_poll_results_message_uses_distinct_voter_denominator_for_multi_select():
    conn = _make_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO polls (question, options_json, status, allow_multiple) VALUES "
        "('Pick any', '[\"a\",\"b\"]', 'closed', 1)"
    )
    poll_id = c.lastrowid
    c.executemany(
        "INSERT INTO poll_votes (poll_id, member_id, option_index) VALUES (?, ?, ?)",
        [(poll_id, 1, 0), (poll_id, 1, 1), (poll_id, 2, 0)],
    )
    conn.commit()

    message = poll_service.build_poll_results_message(conn, poll_id)

    assert "Total selections: *3* from *2* voter(s)" in message
    assert "(100.0%)" in message
