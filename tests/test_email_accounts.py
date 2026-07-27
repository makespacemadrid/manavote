from werkzeug.security import generate_password_hash

from app import create_app
from app.web.routes import auth_routes
from app.web.routes import main_routes


def _app(monkeypatch, db_path):
    monkeypatch.setattr(main_routes, "DB_PATH", str(db_path))
    app = create_app()
    monkeypatch.setitem(app.config, "TESTING", True)
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    return app


def _add_member(username, password, email=None, is_admin=0):
    conn = auth_routes.legacy.get_db()
    cursor = conn.execute(
        "INSERT INTO members (username, password_hash, email, is_admin) VALUES (?, ?, ?, ?)",
        (username, generate_password_hash(password), email, is_admin),
    )
    conn.commit()
    member_id = cursor.lastrowid
    conn.close()
    return member_id


def test_email_can_be_used_to_log_in_case_insensitively(monkeypatch, isolated_db_path):
    monkeypatch.setattr(main_routes, "DB_PATH", str(isolated_db_path))
    _add_member("mail-login-alice", "correct-password", "Alice@Example.org")
    client = _app(monkeypatch, isolated_db_path).test_client()

    response = client.post(
        "/login",
        data={"username": "alice@example.org", "password": "correct-password"},
    )

    assert response.status_code == 302
    assert response.location.endswith("/dashboard")
    with client.session_transaction() as session:
        assert session["username"] == "mail-login-alice"


def test_member_can_add_email_only_once(monkeypatch, isolated_db_path):
    monkeypatch.setattr(main_routes, "DB_PATH", str(isolated_db_path))
    member_id = _add_member("settings-alice", "password")
    client = _app(monkeypatch, isolated_db_path).test_client()
    with client.session_transaction() as session:
        session["member_id"] = member_id
        session["username"] = "settings-alice"
        session["is_admin"] = 0

    response = client.post("/settings", data={"email": "Alice@Example.org"})
    assert response.status_code == 302
    response = client.post("/settings", data={"email": "changed@example.org"})
    assert response.status_code == 302

    conn = auth_routes.legacy.get_db()
    email = conn.execute("SELECT email FROM members WHERE id = ?", (member_id,)).fetchone()["email"]
    conn.close()
    assert email == "alice@example.org"


def test_admin_can_edit_member_username_and_email(monkeypatch, isolated_db_path):
    monkeypatch.setattr(main_routes, "DB_PATH", str(isolated_db_path))
    admin_id = _add_member("email-admin", "password", is_admin=1)
    member_id = _add_member("old-name", "password")
    client = _app(monkeypatch, isolated_db_path).test_client()
    with client.session_transaction() as session:
        session["member_id"] = admin_id
        session["username"] = "email-admin"
        session["is_admin"] = 1

    response = client.post(
        "/admin",
        data={
            "action": "edit_member_identity",
            "member_id": member_id,
            "username": "new-name",
            "email": "New@Example.org",
        },
    )

    assert response.status_code == 200
    conn = auth_routes.legacy.get_db()
    member = conn.execute("SELECT username, email FROM members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    assert dict(member) == {"username": "new-name", "email": "new@example.org"}
