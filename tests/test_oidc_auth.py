import sqlite3

import pytest

from app import create_app
from app.db.migrations import run_migrations
from app.web.routes import auth_routes


def configure_app(monkeypatch, **values):
    app = create_app()
    for key, value in values.items():
        monkeypatch.setitem(app.config, key, value)
    return app


def test_oidc_migration_adds_identity_columns(tmp_path):
    conn = sqlite3.connect(tmp_path / "members.db")
    conn.execute(
        "CREATE TABLE members (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, is_admin INTEGER DEFAULT 0)"
    )
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, amount REAL, title TEXT, basic_supplies INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE activity_log (id INTEGER PRIMARY KEY, description TEXT)")
    run_migrations(conn.cursor())

    columns = {row[1] for row in conn.execute("PRAGMA table_info(members)")}
    assert {"oidc_sub", "email", "display_name"} <= columns
    with pytest.raises(sqlite3.IntegrityError):
        conn.executemany(
            "INSERT INTO members (id, username, password_hash, oidc_sub) VALUES (?, ?, ?, ?)",
            [(1, "one", "x", "same-sub"), (2, "two", "x", "same-sub")],
        )
    conn.close()


def test_oidc_login_is_unavailable_without_client_secret(monkeypatch):
    app = configure_app(monkeypatch, TESTING=True, OIDC_ENABLED=False)

    response = app.test_client().get("/auth/login/keycloak")

    assert response.status_code == 503


def test_oidc_login_uses_configured_public_callback(monkeypatch):
    app = configure_app(
        monkeypatch,
        TESTING=True,
        OIDC_ENABLED=True,
        OIDC_REDIRECT_URI="https://manavote.mksmad.org/auth/callback/keycloak",
    )
    seen = {}

    class FakeClient:
        def authorize_redirect(self, redirect_uri):
            seen["redirect_uri"] = redirect_uri
            return "redirected"

    monkeypatch.setattr(auth_routes.oauth, "keycloak", FakeClient())
    response = app.test_client().get("/auth/login/keycloak")

    assert response.get_data(as_text=True) == "redirected"
    assert seen["redirect_uri"] == "https://manavote.mksmad.org/auth/callback/keycloak"


def test_oidc_callback_rejects_inactive_members(monkeypatch):
    app = configure_app(
        monkeypatch,
        TESTING=True,
        OIDC_ENABLED=True,
        OIDC_REQUIRED_GROUP="members-active",
    )

    class FakeClient:
        def authorize_access_token(self):
            return {"userinfo": {"sub": "inactive", "groups": []}}

    monkeypatch.setattr(auth_routes.oauth, "keycloak", FakeClient())
    response = app.test_client().get("/auth/callback/keycloak")

    assert response.status_code == 403


def test_oidc_callback_rejects_identity_without_subject(monkeypatch):
    app = configure_app(monkeypatch, TESTING=True, OIDC_ENABLED=True)

    class FakeClient:
        def authorize_access_token(self):
            return {"userinfo": {"groups": ["members-active"]}}

    monkeypatch.setattr(auth_routes.oauth, "keycloak", FakeClient())
    assert app.test_client().get("/auth/callback/keycloak").status_code == 400


def test_oidc_callback_establishes_session_without_tokens(monkeypatch):
    app = configure_app(
        monkeypatch,
        TESTING=True,
        OIDC_ENABLED=True,
        OIDC_REQUIRED_GROUP="members-active",
    )

    class FakeClient:
        def authorize_access_token(self):
            return {
                "access_token": "must-not-enter-session",
                "refresh_token": "must-not-enter-session",
                "userinfo": {"sub": "subject", "groups": ["members-active"]},
            }

    monkeypatch.setattr(auth_routes.oauth, "keycloak", FakeClient())
    monkeypatch.setattr(
        auth_routes,
        "_upsert_oidc_member",
        lambda claims: {"id": 42, "username": "alice", "is_admin": 0},
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["lang"] = "es"
        session["oidc_transient"] = "discard-me"

    response = client.get("/auth/callback/keycloak")

    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["member_id"] == 42
        assert session["lang"] == "es"
        assert session["oidc_login"] is True
        assert "access_token" not in session
        assert "refresh_token" not in session
        assert "oidc_transient" not in session


def test_oidc_logout_clears_session_and_uses_configured_redirect(monkeypatch):
    app = configure_app(
        monkeypatch,
        TESTING=True,
        OIDC_ENABLED=True,
        OIDC_CLIENT_ID="manavote",
        OIDC_POST_LOGOUT_REDIRECT_URI="https://manavote.mksmad.org/login",
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 42
        session["oidc_login"] = True

    response = client.get("/logout")

    assert response.status_code == 302
    assert (
        "identity.mksmad.org/realms/Makespace/protocol/openid-connect/logout"
        in response.location
    )
    assert "client_id=manavote" in response.location
    assert "post_logout_redirect_uri=https%3A%2F%2Fmanavote.mksmad.org%2Flogin" in response.location
    with client.session_transaction() as session:
        assert not session


def test_oidc_member_is_provisioned_and_admin_group_is_mapped(isolated_db_path):
    claims = {
        "sub": "stable-keycloak-id",
        "preferred_username": "alice",
        "email": "alice@example.org",
        "name": "Alice Member",
        "groups": ["members-active", "admins"],
        "telegram_handle": "@alice_mks",
    }

    member = auth_routes._upsert_oidc_member(claims)

    assert member["username"] == "alice"
    assert member["is_admin"] == 1
    conn = auth_routes.legacy.get_db()
    stored = conn.execute(
        "SELECT oidc_sub, email, display_name, telegram_username FROM members WHERE id = ?",
        (member["id"],),
    ).fetchone()
    conn.close()
    assert dict(stored) == {
        "oidc_sub": "stable-keycloak-id",
        "email": "alice@example.org",
        "display_name": "Alice Member",
        "telegram_username": "alice_mks",
    }


def test_oidc_member_update_is_idempotent_and_syncs_admin_role(isolated_db_path):
    initial = {
        "sub": "existing-subject",
        "preferred_username": "alice",
        "email": "old@example.org",
        "groups": ["members-active", "admins"],
    }
    first = auth_routes._upsert_oidc_member(initial)
    updated = auth_routes._upsert_oidc_member(
        {
            **initial,
            "preferred_username": "ignored",
            "email": "new@example.org",
            "name": "Updated Name",
            "groups": ["members-active"],
        }
    )

    assert updated["id"] == first["id"]
    assert updated["username"] == "alice"
    assert updated["is_admin"] == 0
    conn = auth_routes.legacy.get_db()
    rows = conn.execute(
        "SELECT email, display_name FROM members WHERE oidc_sub = ?",
        ("existing-subject",),
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert dict(rows[0]) == {"email": "new@example.org", "display_name": "Updated Name"}


def test_oidc_member_does_not_take_existing_local_username(isolated_db_path):
    conn = auth_routes.legacy.get_db()
    conn.execute(
        "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, 0)",
        ("alice", "local-hash"),
    )
    conn.commit()
    conn.close()

    member = auth_routes._upsert_oidc_member(
        {
            "sub": "new-subject",
            "preferred_username": "alice",
            "groups": ["members-active"],
        }
    )

    assert member["username"] == "alice-2"
