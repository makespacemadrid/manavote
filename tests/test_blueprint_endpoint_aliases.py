from app import app


def test_legacy_endpoints_are_registered_after_blueprint_split():
    expected = {
        "index",
        "healthz",
        "login",
        "logout",
        "set_language",
        "change_password",
        "settings_page",
        "telegram_settings",
        "register",
        "api_register",
        "api_create_proposal",
        "api_list_proposals",
        "about",
        "calendar",
        "proposal_detail",
        "polls_page",
        "admin",
    }

    missing = [name for name in expected if name not in app.view_functions]
    assert not missing, f"Missing legacy endpoint aliases: {missing}"


def test_login_route_exposes_both_blueprint_and_legacy_endpoint_names():
    login_view = app.view_functions["auth.login"]
    assert app.view_functions["login"] is login_view


def test_root_redirect_uses_login_url_without_build_error():
    client = app.test_client()
    with client.session_transaction() as session:
        session.clear()
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("Location", "").endswith("/login")


def test_calendar_and_about_expose_blueprint_aliases():
    assert "calendar" in app.view_functions
    assert "proposals.calendar" in app.view_functions
    assert "about" in app.view_functions
    assert "proposals.about" in app.view_functions
