import sqlite3

import pytest

from app.web.routes import api_routes
from app.web.routes.main_routes import app


@pytest.fixture
def feedback_db(tmp_path, monkeypatch):
    path = tmp_path / "feedback.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE members (id INTEGER PRIMARY KEY, username TEXT);
        INSERT INTO members VALUES (1, 'member'), (2, 'admin');
        CREATE TABLE feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER NOT NULL,
            source TEXT NOT NULL, category TEXT NOT NULL, message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT, resolved_by INTEGER
        );
    """)
    conn.close()

    def get_db():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(api_routes.legacy, "get_db", get_db)
    return path


def _login(client, member_id, is_admin=False):
    with client.session_transaction() as session:
        session["member_id"] = member_id
        session["is_admin"] = is_admin


def test_member_can_submit_and_admin_can_triage_feedback(feedback_db):
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    client = app.test_client()
    _login(client, 1)
    created = client.post("/api/feedback", json={"category": "bug", "message": "Buttons overlap"})
    assert created.status_code == 201
    feedback_id = created.get_json()["feedback_id"]

    assert client.get("/api/feedback").status_code == 403
    _login(client, 2, True)
    listed = client.get("/api/feedback?category=bug").get_json()["feedback"]
    assert listed[0]["member_id"] == 1
    resolved = client.patch(f"/api/feedback/{feedback_id}", json={"status": "resolved"})
    assert resolved.status_code == 200


def test_feedback_validation_uses_reason_codes(feedback_db):
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    client = app.test_client()
    _login(client, 1)
    response = client.post("/api/feedback", json={"category": "unknown", "message": "Hi"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_category"
