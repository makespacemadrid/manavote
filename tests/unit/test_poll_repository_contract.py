import json
import sqlite3

from app.repositories.poll_repo import PollRepository


def _setup_polls_table(conn):
    conn.execute(
        """
        CREATE TABLE polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            options_json TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            status TEXT DEFAULT 'open'
        )
        """
    )
    conn.commit()


def test_create_inserts_poll_as_open_with_json_encoded_options():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_polls_table(conn)
    repo = PollRepository(conn)

    poll_id = repo.create("Where should we meet?", ["Room A", "Room B"], created_by=1)

    row = conn.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
    assert row["question"] == "Where should we meet?"
    assert row["status"] == "open"
    assert json.loads(row["options_json"]) == ["Room A", "Room B"]
