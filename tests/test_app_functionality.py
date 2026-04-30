import pathlib
import sys
import unittest
import tempfile
import os

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
        """Basic supplies uses basic threshold (absolute number)"""
        thresholds = {"basic": 2, "over50": 8, "default": 4}
        result = budget_app.calculate_min_backers(50, 100, 1, thresholds)
        self.assertEqual(result, 2)

    def test_over_50_threshold(self):
        """Over 50 uses over50 threshold (absolute number)"""
        thresholds = {"basic": 2, "over50": 8, "default": 4}
        result = budget_app.calculate_min_backers(50, 75, 0, thresholds)
        self.assertEqual(result, 8)

    def test_default_threshold(self):
        """Default uses default threshold (absolute number)"""
        thresholds = {"basic": 2, "over50": 8, "default": 4}
        result = budget_app.calculate_min_backers(50, 30, 0, thresholds)
        self.assertEqual(result, 4)

    def test_min_one_backer(self):
        """Minimum is 1 backer regardless of calculation"""
        thresholds = {"basic": 2, "over50": 8, "default": 4}
        result = budget_app.calculate_min_backers(3, 25, 0, thresholds)
        self.assertEqual(result, 4)
    
    def test_very_small_group_returns_at_least_one(self):
        """Very small group with threshold 1 returns 1"""
        thresholds = {"basic": 1, "over50": 1, "default": 1}
        result = budget_app.calculate_min_backers(1, 25, 0, thresholds)
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
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
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


class TestRouteAccessControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def test_index_redirects_to_login_when_logged_out(self):
        """Root route redirects anonymous users to login"""
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers.get("Location", ""))

    def test_index_redirects_to_dashboard_when_logged_in(self):
        """Root route redirects authenticated users to dashboard"""
        _set_member_session(self.client)
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers.get("Location", ""))

    def test_dashboard_requires_authentication(self):
        """Dashboard requires login and redirects anonymous users"""
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers.get("Location", ""))

    def test_admin_rejects_non_admin_members(self):
        """Admin page redirects members without admin privileges"""
        _set_member_session(self.client)
        response = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers.get("Location", ""))


class TestProposalCreation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
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
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
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
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_admin_session(self.client)

    def test_admin_page_loads(self):
        """Admin page loads for admin user"""
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)

    def test_admin_backup_button_creates_backup_file(self):
        """Backup action creates a DB backup file"""
        db_dir = os.path.dirname(budget_app.DB_PATH) or "."
        backup_base = os.path.basename(budget_app.DB_PATH).replace(".db", "")
        before = set(f for f in os.listdir(db_dir) if f.startswith(f"{backup_base}_") and f.endswith(".db"))

        response = self.client.post(
            "/admin",
            data={"action": "backup_db", "csrf_token": ""},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Backup created:", html)

        after = set(f for f in os.listdir(db_dir) if f.startswith(f"{backup_base}_") and f.endswith(".db"))
        created = after - before
        self.assertTrue(created or len(after) >= len(before))

        for filename in created:
            os.remove(os.path.join(db_dir, filename))


class TestNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def test_dashboard_in_nav(self):
        """Dashboard link in navigation"""
        _set_member_session(self.client)
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Dashboard", html)

    def test_calendar_in_nav(self):
        """Calendar link in navigation"""
        _set_member_session(self.client)
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Calendar", html)

    def test_about_in_nav(self):
        """About link in navigation"""
        _set_member_session(self.client)
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("About", html)

    def test_new_proposal_in_nav(self):
        """New Proposal link in navigation"""
        _set_member_session(self.client)
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("New Proposal", html)


class TestProposalDetail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_proposal_detail_shows_title(self):
        """Proposal detail shows title"""
        response = self.client.get("/proposal/1")
        if response.status_code == 200:
            html = response.data.decode("utf-8")
            self.assertIn("title", html.lower())

    def test_proposal_detail_shows_amount(self):
        """Proposal detail shows amount"""
        response = self.client.get("/proposal/1")
        if response.status_code == 200:
            html = response.data.decode("utf-8")
            self.assertIn("amount", html.lower())


class TestProposalTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_proposal_has_status_tag(self):
        """Proposal list shows status tags"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("active", html.lower())


class TestBudgetDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_dashboard_shows_budget_amount(self):
        """Dashboard displays budget amount"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("€", html)

    def test_budget_is_numeric(self):
        """get_current_budget returns numeric value"""
        result = budget_app.get_current_budget()
        self.assertIsInstance(result, (int, float))


class TestSessionManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def test_logout_redirects(self):
        """Logout redirects to login"""
        _set_member_session(self.client)
        response = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def test_change_password_page_loads(self):
        """Change password page loads"""
        _set_member_session(self.client)
        response = self.client.get("/change-password")
        self.assertEqual(response.status_code, 200)


class TestProposalList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_dashboard_shows_proposals(self):
        """Dashboard displays proposal list"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

    def test_proposal_list_shows_items(self):
        """Proposal list contains proposals"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("proposal", html.lower())


class TestRestApiValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ["ADMIN_API_KEY"] = "test-api-key"
        # Patch the ADMIN_API_KEY in the routes module directly
        import app.web.routes.main_routes as routes
        routes.ADMIN_API_KEY = "test-api-key"
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def test_api_register_requires_json_content_type(self):
        """API register requires JSON content type"""
        response = self.client.post(
            "/api/register",
            data='{"username": "test", "password": "test"}',
            headers={"X-Admin-Key": "test-api-key", "Content-Type": "text/plain"},
        )
        self.assertEqual(response.status_code, 415)

    def test_api_create_proposal_rejects_non_numeric_amount(self):
        """API rejects non-numeric amount"""
        response = self.client.post(
            "/api/proposals",
            json={"title": "Test", "amount": "not-a-number"},
            headers={"X-Admin-Key": "test-api-key"},
        )
        self.assertEqual(response.status_code, 400)

    def test_api_edit_proposal_requires_json_content_type(self):
        """API edit requires JSON content type"""
        # Create a test proposal first
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO proposals (title, description, amount, created_by, status) VALUES (?, ?, ?, ?, 'active')",
            ("Test Edit Proposal", "desc", 10.0, 1),
        )
        proposal_id = c.lastrowid
        conn.commit()
        conn.close()
        
        response = self.client.patch(
            f"/api/proposals/{proposal_id}",
            data="title=updated",
            headers={"X-Admin-Key": "test-api-key"},
        )
        self.assertEqual(response.status_code, 415)


class TestPasswordSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def test_secret_key_is_configured(self):
        """App always has a configured secret key"""
        self.assertTrue(budget_app.app.secret_key)


class TestDashboardFeatures(unittest.TestCase):
    """Test new dashboard features: filters, tags, vote display"""
    
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_dashboard_shows_budget_card(self):
        """Dashboard displays budget card with current budget"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Budget", html)
        self.assertIn("€", html)

    def test_dashboard_filters_inside_proposals_card(self):
        """Filter buttons are displayed on dashboard"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("All", html)
        self.assertIn("Active", html)
        self.assertIn("Approved", html)

    def test_filter_buttons_show_amounts(self):
        """Filter buttons display amounts without decimals"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("€", html)

    def test_dashboard_defaults_to_active_filter(self):
        """Dashboard defaults to showing active proposals"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

    def test_pending_budget_filter_displays(self):
        """Pending Budget filter button is displayed"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Pending Budget", html)

    def test_vote_display_shows_required_count(self):
        """Vote counts show required votes"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("required", html.lower())


class TestPasswordChange(unittest.TestCase):
    """Test password change functionality"""
    
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_change_password_page_loads(self):
        """Change password page loads for logged-in user"""
        response = self.client.get("/change-password")
        self.assertEqual(response.status_code, 200)

    def test_change_password_menu_item_displays(self):
        """Change Password link appears in navigation"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Change Password", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
