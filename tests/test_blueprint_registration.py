from app import create_app


def test_create_app_is_idempotent_for_blueprint_registration():
    app1 = create_app()
    app2 = create_app()
    assert app1 is app2
    assert app1.extensions.get("manavote_blueprints_registered") is True
