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
