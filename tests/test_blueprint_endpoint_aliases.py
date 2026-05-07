from app import app


def test_legacy_endpoints_are_registered_after_blueprint_split():
    expected = {
        "login",
        "logout",
        "set_language",
        "change_password",
        "api_register",
        "api_create_proposal",
        "api_list_proposals",
        "proposal_detail",
        "polls_page",
        "admin",
    }

    missing = [name for name in expected if name not in app.view_functions]
    assert not missing, f"Missing legacy endpoint aliases: {missing}"
