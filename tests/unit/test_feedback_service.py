import logging
import sqlite3

import pytest

from app.services.feedback_service import (
    FeedbackValidationError,
    list_feedback,
    submit_feedback,
    update_feedback_status,
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE members (id INTEGER PRIMARY KEY, username TEXT);
        INSERT INTO members VALUES (1, 'member'), (2, 'admin');
        CREATE TABLE feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER NOT NULL,
            source TEXT NOT NULL, category TEXT NOT NULL, message TEXT NOT NULL,
            section TEXT,
            status TEXT NOT NULL DEFAULT 'new', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT, resolved_by INTEGER
        );
    """)
    yield connection
    connection.close()


def test_submit_list_and_resolve_feedback(conn, caplog):
    with caplog.at_level(logging.INFO):
        feedback_id = submit_feedback(
            conn, member_id=1, source="web", category="bug",
            message="The vote button overlaps", logger=logging.getLogger("feedback-test"),
            section="/proposals/42",
        )
        update_feedback_status(
            conn, feedback_id=feedback_id, status="resolved", resolved_by=2,
            logger=logging.getLogger("feedback-test"),
        )

    item = list_feedback(conn, status="resolved")[0]
    assert item["message"] == "The vote button overlaps"
    assert item["section"] == "/proposals/42"
    assert item["resolved_by_username"] == "admin"
    assert item["resolved_at"] is not None
    assert "event=feedback_submitted" in caplog.text
    assert "section=/proposals/42" in caplog.text
    assert "event=feedback_status_changed" in caplog.text


@pytest.mark.parametrize(
    ("category", "message", "code"),
    [("unknown", "hello", "invalid_category"), ("bug", "", "message_required")],
)
def test_submit_feedback_validation(conn, category, message, code):
    with pytest.raises(FeedbackValidationError) as exc:
        submit_feedback(conn, member_id=1, source="web", category=category, message=message)
    assert exc.value.code == code
