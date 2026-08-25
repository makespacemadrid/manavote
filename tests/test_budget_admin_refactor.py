import pathlib
import sys
import unittest
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app as budget_app


def _set_admin_session(client):
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["username"] = "admin"
        session["is_admin"] = 1


def _reset_rate_limits_for_test_client():
    try:
        budget_app.limiter.reset()
    except Exception:
        pass


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

    def test_migrations_seed_default_vote_modes_when_missing(self):
        with _temporary_db():
            conn = budget_app.get_db()
            conn.execute("DELETE FROM settings WHERE key IN ('poll_vote_mode', 'proposal_vote_mode')")
            conn.commit()
            conn.close()

            # Re-open DB to trigger migration seed safeguards.
            conn = budget_app.get_db()
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key = 'poll_vote_mode'")
            poll_mode = c.fetchone()
            c.execute("SELECT value FROM settings WHERE key = 'proposal_vote_mode'")
            proposal_mode = c.fetchone()
            conn.close()

            self.assertIsNotNone(poll_mode)
            self.assertIsNotNone(proposal_mode)
            self.assertEqual(poll_mode["value"], "both")
            self.assertEqual(proposal_mode["value"], "both")
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
            _reset_rate_limits_for_test_client()

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
            _reset_rate_limits_for_test_client()

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
            self.assertIn("Budget item recorded: €10.00. New balance:", page)
            self.assertNotIn("Monthly top-up applied!", page)

    def test_add_budget_accepts_negative_items(self):
        with _temporary_db():
            conn = budget_app.get_db()
            starting_budget = budget_app.get_current_budget()
            conn.close()

            client = budget_app.app.test_client()
            _set_admin_session(client)
            _reset_rate_limits_for_test_client()

            response = client.post(
                "/admin",
                data={
                    "action": "add_budget",
                    "amount": "-20",
                    "description": "Cash stolen",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(
                "Budget item recorded: €-20.00.", response.data.decode("utf-8")
            )

            conn = budget_app.get_db()
            row = conn.execute(
                "SELECT amount, description FROM activity_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            self.assertEqual(row["amount"], -20)
            self.assertEqual(row["description"], "Cash stolen")
            self.assertEqual(budget_app.get_current_budget(), starting_budget - 20)

    def test_add_budget_rejects_zero_items(self):
        with _temporary_db():
            client = budget_app.app.test_client()
            _set_admin_session(client)
            _reset_rate_limits_for_test_client()

            response = client.post(
                "/admin",
                data={"action": "add_budget", "amount": "0", "description": "Nothing"},
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("Amount must be non-zero", response.data.decode("utf-8"))

    def test_add_budget_reprocesses_over_budget_proposals(self):
        with _temporary_db():
            conn = budget_app.get_db()
            c = conn.cursor()
            c.execute("DELETE FROM activity_log")
            c.execute("INSERT INTO proposals (title, description, amount, created_by, status) VALUES (?, ?, ?, ?, ?)", ("Needs budget", "x", 30, 1, "active"))
            proposal_id = c.lastrowid
            c.execute("INSERT INTO votes (proposal_id, member_id, vote) VALUES (?, ?, 'in_favor')", (proposal_id, 1))
            conn.commit()
            conn.close()

            budget_app.process_proposal(proposal_id)

            conn = budget_app.get_db()
            c = conn.cursor()
            c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
            self.assertEqual(c.fetchone()["status"], "over_budget")
            conn.close()

            client = budget_app.app.test_client()
            _set_admin_session(client)
            _reset_rate_limits_for_test_client()
            response = client.post(
                "/admin",
                data={"action": "add_budget", "amount": "50", "description": "top up for pending"},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)

            conn = budget_app.get_db()
            c = conn.cursor()
            c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
            self.assertEqual(c.fetchone()["status"], "approved")
            conn.close()

    def test_proposal_age_filters_split_active_proposals(self):
        with _temporary_db():
            conn = budget_app.get_db()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            conn.executemany(
                "INSERT INTO proposals (title, description, amount, created_by, status, created_at, image_filename) VALUES (?, 'x', ?, 1, 'active', ?, ?)",
                [
                    ("Recent proposal", 10, (now - timedelta(days=29)).isoformat(), "recent.png"),
                    ("Old proposal", 20, (now - timedelta(days=31)).isoformat(), "old.png"),
                    ("Very old proposal", 30, (now - timedelta(days=95)).isoformat(), "very-old.png"),
                ],
            )
            conn.commit()
            conn.close()

            client = budget_app.app.test_client()
            _set_admin_session(client)

            recent_html = client.get("/proposals?filter=recent").data.decode("utf-8")
            self.assertIn("Recent proposal", recent_html)
            self.assertNotIn("Old proposal", recent_html)

            old_html = client.get("/proposals?filter=old").data.decode("utf-8")
            self.assertNotIn("Recent proposal", old_html)
            self.assertIn("Old proposal", old_html)
            self.assertIn("Very old proposal", old_html)
            self.assertIn(">old</span>", old_html)
            self.assertIn("Over 30 days old", old_html)
            self.assertIn("Over 90 days old", old_html)
            self.assertIn("proposal-age-watermark", old_html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
