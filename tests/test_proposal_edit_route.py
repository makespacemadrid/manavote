import app as budget_app


def test_edit_proposal_page_loads_for_owner(isolated_db_path):
    budget_app.app.config["TESTING"] = True
    budget_app.app.config["WTF_CSRF_ENABLED"] = False
    budget_app.init_db()

    client = budget_app.app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["username"] = "owner"
        session["is_admin"] = 0

    conn = budget_app.get_db()
    conn.execute(
        "INSERT OR REPLACE INTO members (id, username, password_hash) VALUES (?, ?, ?)",
        (1, "owner", "hash"),
    )
    cursor = conn.execute(
        "INSERT INTO proposals (title, description, amount, created_by) VALUES (?, ?, ?, ?)",
        ("Editable proposal", "Original description", 12.50, 1),
    )
    proposal_id = cursor.lastrowid
    conn.commit()
    conn.close()

    response = client.get(f"/proposal/{proposal_id}/edit")

    assert response.status_code == 200
    assert b"Editable proposal" in response.data


def test_edit_comment_page_loads_for_admin(isolated_db_path):
    budget_app.app.config["TESTING"] = True
    budget_app.app.config["WTF_CSRF_ENABLED"] = False
    budget_app.init_db()

    client = budget_app.app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["username"] = "admin"
        session["is_admin"] = 1

    conn = budget_app.get_db()
    conn.execute(
        "INSERT OR REPLACE INTO members (id, username, password_hash, is_admin) VALUES (?, ?, ?, ?)",
        (1, "admin", "hash", 1),
    )
    proposal_cursor = conn.execute(
        "INSERT INTO proposals (title, description, amount, created_by) VALUES (?, ?, ?, ?)",
        ("Commented proposal", "Original description", 12.50, 1),
    )
    comment_cursor = conn.execute(
        "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
        (proposal_cursor.lastrowid, 1, "Editable comment"),
    )
    comment_id = comment_cursor.lastrowid
    conn.commit()
    conn.close()

    response = client.get(f"/comment/{comment_id}/edit")

    assert response.status_code == 200
    assert b"Editable comment" in response.data
