import app
from app.web.routes import main_routes


def _headers():
    return {"X-Admin-Key": "test-admin-key"}


def _set_admin_key():
    app.ADMIN_API_KEY = "test-admin-key"
    main_routes.ADMIN_API_KEY = "test-admin-key"


def test_api_register_uses_error_envelope_for_validation_errors():
    _set_admin_key()
    client = app.app.test_client()
    response = client.post("/api/register", json={"username": "only"}, headers=_headers())
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "username_password_required"


def test_api_create_proposal_uses_error_envelope_for_validation_errors():
    _set_admin_key()
    client = app.app.test_client()
    response = client.post("/api/proposals", json={"title": "x"}, headers=_headers())
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] in {"title_amount_required", "amount_must_be_positive"}


def test_api_get_proposal_uses_error_envelope_for_not_found():
    _set_admin_key()
    client = app.app.test_client()
    response = client.get("/api/proposals/999999", headers=_headers())
    assert response.status_code == 404
    error = response.get_json()["error"]
    assert error["code"] == "proposal_not_found"


def test_api_list_proposals_invalid_status_uses_error_envelope():
    _set_admin_key()
    client = app.app.test_client()
    response = client.get("/api/proposals?status=bogus", headers=_headers())
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "invalid_status_filter"


def test_api_list_proposals_rejects_legacy_non_domain_status():
    _set_admin_key()
    client = app.app.test_client()
    response = client.get("/api/proposals?status=accepted", headers=_headers())
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_status_filter"


def test_api_list_proposals_invalid_age_uses_error_envelope():
    _set_admin_key()
    client = app.app.test_client()
    response = client.get("/api/proposals?age=ancient", headers=_headers())
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_age_filter"


def test_api_list_proposals_rejects_age_with_non_active_status():
    _set_admin_key()
    client = app.app.test_client()
    response = client.get("/api/proposals?age=old&status=approved", headers=_headers())
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "incompatible_proposal_filters"


def test_api_list_proposals_counts_canonical_vote_values():
    _set_admin_key()
    conn = main_routes.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO proposals (title, amount, created_by, status) VALUES (?, ?, ?, 'active')",
        ("API vote count contract", 10, 1),
    )
    proposal_id = cursor.lastrowid
    cursor.executemany(
        "INSERT INTO votes (proposal_id, member_id, vote) VALUES (?, ?, ?)",
        [(proposal_id, -10001, "in_favor"), (proposal_id, -10002, "against")],
    )
    conn.commit()
    conn.close()

    try:
        response = app.app.test_client().get("/api/proposals?status=active", headers=_headers())
        assert response.status_code == 200
        proposal = next(item for item in response.get_json()["proposals"] if item["id"] == proposal_id)
        assert proposal["yes_votes"] == 1
        assert proposal["no_votes"] == 1
    finally:
        conn = main_routes.get_db()
        conn.execute("DELETE FROM votes WHERE proposal_id = ?", (proposal_id,))
        conn.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
        conn.commit()
        conn.close()


def test_api_create_proposal_creator_errors_use_error_envelope():
    _set_admin_key()
    client = app.app.test_client()

    missing = client.post("/api/proposals", json={"title": "New item", "amount": 10}, headers=_headers())
    unknown = client.post(
        "/api/proposals",
        json={"title": "New item", "amount": 10, "created_by": 999999},
        headers=_headers(),
    )

    assert missing.status_code == 400
    assert missing.get_json()["error"]["code"] == "created_by_required"
    assert unknown.status_code == 404
    assert unknown.get_json()["error"]["code"] == "creator_member_not_found"


def test_api_create_poll_validation_uses_error_envelope():
    _set_admin_key()
    client = app.app.test_client()

    cases = [
        ({"question": "no", "options": ["A", "B"], "created_by": 1}, "invalid_poll_question"),
        ({"question": "Valid question", "options": "A,B", "created_by": 1}, "invalid_poll_options"),
        ({"question": "Valid question", "options": ["A", "B"]}, "created_by_required"),
    ]
    for payload, code in cases:
        response = client.post("/api/polls", json=payload, headers=_headers())
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == code
