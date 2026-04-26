import pathlib
import sys
import unittest
import tempfile
from contextlib import contextmanager

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app as budget_app


def _set_admin_session(client):
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["username"] = "admin"
        session["is_admin"] = 1


@contextmanager
def _temporary_db():
    from app.db import connection
    from app.web.routes import main_routes

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = str(pathlib.Path(tmp_dir) / "test_budget_admin_refactor.db")

        old_db_conn = connection.DB_PATH
        old_db_routes = main_routes.DB_PATH
        old_db_package = budget_app.DB_PATH

        connection.DB_PATH = test_db
        main_routes.DB_PATH = test_db
        budget_app.DB_PATH = test_db

        try:
            budget_app.init_db()
            yield test_db
        finally:
            connection.DB_PATH = old_db_conn
            main_routes.DB_PATH = old_db_routes
            budget_app.DB_PATH = old_db_package


class TestBudgetAdminRefactor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False

    def test_calculate_min_backers_threshold_variants(self):
        thresholds = {"basic": 5, "over50": 20, "default": 10}

        self.assertEqual(budget_app.calculate_min_backers(50, 15, 1, thresholds), 2)
        self.assertEqual(budget_app.calculate_min_backers(50, 75, 0, thresholds), 10)
        self.assertEqual(budget_app.calculate_min_backers(50, 25, 0, thresholds), 5)
        self.assertEqual(budget_app.calculate_min_backers(3, 25, 0, thresholds), 1)

    def test_get_setting_float_uses_default_when_invalid(self):
        with _temporary_db():
            conn = budget_app.get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'monthly_topup'",
                ("oops",),
            )
            conn.commit()
            conn.close()

            self.assertEqual(
                budget_app.get_setting_float("monthly_topup", 50), 50.0
            )

    def test_trigger_monthly_uses_monthly_topup_setting(self):
        with _temporary_db():
            conn = budget_app.get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'monthly_topup'",
                ("75",),
            )
            conn.commit()
            conn.close()

            client = budget_app.app.test_client()
            _set_admin_session(client)

            response = client.post(
                "/admin",
                data={"action": "trigger_monthly"},
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            page = response.data.decode("utf-8")
            self.assertIn("Monthly top-up applied! New budget:", page)

            conn = budget_app.get_db()
            c = conn.cursor()
            c.execute("SELECT amount, description FROM activity_log ORDER BY id DESC LIMIT 1")
            amount, description = c.fetchone()
            conn.close()
            self.assertEqual(amount, 75)
            self.assertEqual(description, "Monthly top-up")

    def test_add_budget_does_not_show_monthly_flash_message(self):
        with _temporary_db():
            client = budget_app.app.test_client()
            _set_admin_session(client)

            response = client.post(
                "/admin",
                data={
                    "action": "add_budget",
                    "amount": "10",
                    "description": "Test budget entry",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            page = response.data.decode("utf-8")
            self.assertIn("Added €10.0 to budget! New balance:", page)
            self.assertNotIn("Monthly top-up applied!", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
