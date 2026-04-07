import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app as budget_app


def _set_admin_session(client):
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["username"] = "admin"
        session["is_admin"] = 1


def test_calculate_min_backers_threshold_variants():
    thresholds = {"basic": 5, "over50": 20, "default": 10}

    assert budget_app.calculate_min_backers(50, 15, 1, thresholds) == 2
    assert budget_app.calculate_min_backers(50, 75, 0, thresholds) == 10
    assert budget_app.calculate_min_backers(50, 25, 0, thresholds) == 5
    assert budget_app.calculate_min_backers(3, 25, 0, thresholds) == 1


def test_get_setting_float_uses_default_when_invalid(tmp_path):
    budget_app.DB_PATH = str(tmp_path / "test_invalid_float.db")
    budget_app.init_db()

    conn = budget_app.get_db()
    c = conn.cursor()
    c.execute("UPDATE settings SET value = ? WHERE key = 'monthly_topup'", ("oops",))
    conn.commit()
    conn.close()

    assert budget_app.get_setting_float("monthly_topup", 50) == 50.0


def test_trigger_monthly_uses_monthly_topup_setting(tmp_path):
    budget_app.DB_PATH = str(tmp_path / "test_monthly_topup.db")
    budget_app.app.config["TESTING"] = True
    budget_app.init_db()

    conn = budget_app.get_db()
    c = conn.cursor()
    c.execute("UPDATE settings SET value = '100' WHERE key = 'current_budget'")
    c.execute("UPDATE settings SET value = '25' WHERE key = 'monthly_topup'")
    conn.commit()
    conn.close()

    client = budget_app.app.test_client()
    _set_admin_session(client)

    response = client.post(
        "/admin", data={"action": "trigger_monthly"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert budget_app.get_current_budget() == 125.0


def test_add_budget_does_not_show_monthly_flash_message(tmp_path):
    budget_app.DB_PATH = str(tmp_path / "test_add_budget_flash.db")
    budget_app.app.config["TESTING"] = True
    budget_app.init_db()

    client = budget_app.app.test_client()
    _set_admin_session(client)

    response = client.post(
        "/admin",
        data={"action": "add_budget", "amount": "10", "description": "Donation"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert "Added €10.0 to budget! New balance:" in page
    assert "Monthly top-up triggered!" not in page
