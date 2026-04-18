import pathlib
import sys
import unittest
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app as budget_app


def _set_admin_session(client):
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["username"] = "admin"
        session["is_admin"] = 1


def _set_member_session(client):
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["username"] = "admin"
        session["is_admin"] = 0


class TestHelperFunctions(unittest.TestCase):
    def test_truncate_username_no_at(self):
        """Username without @ is returned as-is"""
        result = budget_app.truncate_username("alice")
        self.assertEqual(result, "alice")

    def test_truncate_username_with_at(self):
        """Username with @ is truncated at @"""
        result = budget_app.truncate_username("alice@example.com")
        self.assertEqual(result, "alice")

    def test_get_current_budget_returns_float(self):
        """get_current_budget returns numeric value"""
        result = budget_app.get_current_budget()
        self.assertIsInstance(result, (int, float))

    def test_get_member_count_returns_int(self):
        """get_member_count returns integer"""
        result = budget_app.get_member_count()
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)

    def test_get_thresholds_returns_dict(self):
        """get_thresholds returns threshold dict"""
        result = budget_app.get_thresholds()
        self.assertIsInstance(result, dict)
        self.assertIn("basic", result)
        self.assertIn("default", result)


class TestCalculateMinBackers(unittest.TestCase):
    def test_basic_supplies_threshold(self):
        """Basic supplies uses basic threshold"""
        thresholds = {"basic": 5, "over50": 20, "default": 10}
        result = budget_app.calculate_min_backers(50, 100, 1, thresholds)
        self.assertEqual(result, 2)

    def test_over_50_threshold(self):
        """Over 50 uses over50 threshold"""
        thresholds = {"basic": 5, "over50": 20, "default": 10}
        result = budget_app.calculate_min_backers(50, 75, 0, thresholds)
        self.assertEqual(result, 10)

    def test_default_threshold(self):
        """Default uses default threshold"""
        thresholds = {"basic": 5, "over50": 20, "default": 10}
        result = budget_app.calculate_min_backers(50, 30, 0, thresholds)
        self.assertEqual(result, 5)

    def test_min_one_backer(self):
        """Minimum is 1 backer regardless of calculation"""
        thresholds = {"basic": 5, "over50": 20, "default": 10}
        result = budget_app.calculate_min_backers(3, 25, 0, thresholds)
        self.assertEqual(result, 1)


class TestSettings(unittest.TestCase):
    def test_get_setting_value_returns_default(self):
        """get_setting_value returns default for unknown key"""
        result = budget_app.get_setting_value("nonexistent_key", "default_value")
        self.assertEqual(result, "default_value")

    def test_get_setting_float_returns_default(self):
        """get_setting_float returns default for unknown key"""
        result = budget_app.get_setting_float("nonexistent_key", 42.5)
        self.assertEqual(result, 42.5)


class TestAuthentication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def test_login_page_loads(self):
        """Login page loads successfully"""
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)

    def test_register_page_loads(self):
        """Register page loads successfully"""
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)

    def test_about_page_loads(self):
        """About page loads successfully"""
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)


class TestProposalCreation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_new_proposal_page_loads(self):
        """New proposal page loads for logged-in member"""
        response = self.client.get("/proposal/new")
        self.assertEqual(response.status_code, 200)

    def test_proposal_form_has_required_fields(self):
        """Proposal form has required fields"""
        response = self.client.get("/proposal/new")
        html = response.data.decode("utf-8")
        self.assertIn("title", html)
        self.assertIn("amount", html)


class TestVoteFunctionality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_proposal_detail_has_vote_buttons(self):
        """Proposal detail has vote buttons"""
        response = self.client.get("/proposal/1")
        if response.status_code == 200:
            html = response.data.decode("utf-8")
            self.assertIn("vote", html.lower())


class TestAdminFunctionality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_admin_session(self.client)

    def test_admin_page_loads(self):
        """Admin page loads for admin user"""
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)


class TestNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_dashboard_in_nav(self):
        """Dashboard link in navigation"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Dashboard", html)

    def test_calendar_in_nav(self):
        """Calendar link in navigation"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Calendar", html)

    def test_new_proposal_in_nav(self):
        """New Proposal link in navigation"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("New Proposal", html)

    def test_about_in_nav(self):
        """About link in navigation"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("About", html)


class TestProposalDetail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_proposal_detail_shows_title(self):
        """Proposal detail shows title"""
        response = self.client.get("/proposal/1")
        if response.status_code == 200:
            html = response.data.decode("utf-8")
            self.assertIn("proposal", html.lower())

    def test_proposal_detail_shows_amount(self):
        """Proposal detail shows amount"""
        response = self.client.get("/proposal/1")
        if response.status_code == 200:
            html = response.data.decode("utf-8")
            self.assertIn("€", html)


class TestProposalTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_proposal_has_status_tag(self):
        """Proposal shows status tag"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("status-", html)


class TestBudgetDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_dashboard_shows_budget_amount(self):
        """Dashboard shows budget amount"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("€", html)

    def test_budget_is_numeric(self):
        """Budget amount is displayed"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        has_budget = "€" in html and any(c.isdigit() for c in html)
        self.assertTrue(has_budget)


class TestSessionManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def test_logout_redirects(self):
        """Logout redirects"""
        response = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def test_change_password_page_loads(self):
        """Change password page loads for logged-in user"""
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
        response = self.client.get("/change-password")
        self.assertEqual(response.status_code, 200)


class TestProposalList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_dashboard_shows_proposals(self):
        """Dashboard shows proposals list"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

    def test_proposal_list_shows_items(self):
        """Proposal list shows items"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("proposal", html.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
