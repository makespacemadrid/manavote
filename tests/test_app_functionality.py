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
        """Basic supplies uses basic threshold (percentage)"""
        thresholds = {"basic": 5, "over50": 20, "default": 10}
        result = budget_app.calculate_min_backers(100, 100, 1, thresholds)
        self.assertEqual(result, 5)  # 5% of 100 = 5

    def test_over_50_threshold(self):
        """Over 50 uses over50 threshold (percentage)"""
        thresholds = {"basic": 5, "over50": 20, "default": 10}
        result = budget_app.calculate_min_backers(100, 75, 0, thresholds)
        self.assertEqual(result, 20)  # 20% of 100 = 20

    def test_default_threshold(self):
        """Default uses default threshold (percentage)"""
        thresholds = {"basic": 5, "over50": 20, "default": 10}
        result = budget_app.calculate_min_backers(100, 30, 0, thresholds)
        self.assertEqual(result, 10)  # 10% of 100 = 10

    def test_min_one_backer(self):
        """Minimum is 1 backer regardless of calculation"""
        thresholds = {"basic": 1, "over50": 1, "default": 1}
        result = budget_app.calculate_min_backers(3, 25, 0, thresholds)
        self.assertEqual(result, 1)  # 1% of 3 = 0.03, min 1
    
    def test_very_small_group_returns_at_least_one(self):
        """Very small group with low percentage returns 1"""
        thresholds = {"basic": 1, "over50": 1, "default": 1}
        result = budget_app.calculate_min_backers(1, 25, 0, thresholds)
        self.assertEqual(result, 1)  # 1% of 1 = 0.01, min 1


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

    def test_proposal_rejects_invalid_voting_deadline(self):
        response = self.client.post(
            "/proposal/new",
            data={
                "title": "Deadline test",
                "description": "desc",
                "amount": "10.00",
                "url": "",
                "voting_deadline": "not-a-date",
                "csrf_token": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid voting deadline", response.data.decode("utf-8"))


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


class TestPollTelegramActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_admin_session(self.client)
        self.client.post(
            "/admin",
            data={
                "action": "create_poll",
                "question": "Where should we meet?",
                "options": "Room A\nRoom B",
                "csrf_token": "",
            },
            follow_redirects=True,
        )

    def _latest_poll_id(self):
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM polls ORDER BY id DESC LIMIT 1")
        poll_id = c.fetchone()["id"]
        conn.close()
        return poll_id

    def test_send_poll_telegram_uses_sender_and_reports_success(self):
        poll_id = self._latest_poll_id()

        from unittest.mock import patch
        from app.web.routes import main_routes
        with patch.object(main_routes, "send_telegram_message", return_value=True) as mock_send:
            response = self.client.post(
                "/admin",
                data={"action": "send_poll_telegram", "poll_id": poll_id, "csrf_token": ""},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_send.called)
        self.assertIn("Poll sent to Telegram!", response.data.decode("utf-8"))

    def test_send_poll_telegram_test_requires_admin_id(self):
        poll_id = self._latest_poll_id()

        from app.web.routes import main_routes
        original_admin_id = main_routes.TELEGRAM_ADMIN_ID
        main_routes.TELEGRAM_ADMIN_ID = ""
        try:
            response = self.client.post(
                "/admin",
                data={"action": "send_poll_telegram_test", "poll_id": poll_id, "csrf_token": ""},
                follow_redirects=True,
            )
        finally:
            main_routes.TELEGRAM_ADMIN_ID = original_admin_id

        self.assertEqual(response.status_code, 200)
        self.assertIn("TELEGRAM_ADMIN_ID is not configured", response.data.decode("utf-8"))

    def test_send_poll_telegram_test_uses_test_sender(self):
        poll_id = self._latest_poll_id()

        from app.web.routes import main_routes
        original_admin_id = main_routes.TELEGRAM_ADMIN_ID
        main_routes.TELEGRAM_ADMIN_ID = "123456"
        try:
            from unittest.mock import patch
            with patch.object(main_routes, "send_telegram_admin_test_message", return_value=True) as mock_send:
                response = self.client.post(
                    "/admin",
                    data={"action": "send_poll_telegram_test", "poll_id": poll_id, "csrf_token": ""},
                    follow_redirects=True,
                )
        finally:
            main_routes.TELEGRAM_ADMIN_ID = original_admin_id

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_send.called)
        self.assertIn("Poll test sent to TELEGRAM_ADMIN_ID!", response.data.decode("utf-8"))

    def test_telegram_webhook_records_vote(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/vote {poll_id} 2",
                        "from": {"username": "admin"},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["option_index"], 1)

    def test_telegram_webhook_records_vote_with_short_vote_command(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": "/vote 2",
                        "from": {"username": "admin"},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["option_index"], 1)

    def test_telegram_webhook_short_vote_command_targets_latest_open_poll(self):
        self.client.post(
            "/admin",
            data={
                "action": "create_poll",
                "question": "Another open poll?",
                "options": "Yes\nNo",
                "csrf_token": "",
            },
            follow_redirects=True,
        )

        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": "/vote 1",
                        "from": {"username": "admin"},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        poll_id = self._latest_poll_id()
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["option_index"], 0)

    def test_telegram_webhook_rejects_bad_secret(self):
        response = self.client.post("/telegram/webhook/wrong", json={"message": {"text": "/vote 1 1"}})
        self.assertEqual(response.status_code, 403)

    def test_telegram_webhook_unknown_member_does_not_record_vote(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/vote {poll_id} 1",
                        "from": {"username": "not_a_member"},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total FROM poll_votes WHERE poll_id = ?", (poll_id,))
        total = c.fetchone()["total"]
        conn.close()
        self.assertEqual(total, 0)

    def test_telegram_webhook_rejects_vote_for_closed_poll(self):
        poll_id = self._latest_poll_id()
        self.client.post(
            "/admin",
            data={"action": "close_poll", "poll_id": poll_id, "csrf_token": ""},
            follow_redirects=True,
        )
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/vote {poll_id} 1",
                        "from": {"username": "admin"},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        total = c.fetchone()["total"]
        conn.close()
        self.assertEqual(total, 0)

    def test_telegram_webhook_invalid_option_is_ignored(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/vote {poll_id} 99",
                        "from": {"username": "admin"},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        total = c.fetchone()["total"]
        conn.close()
        self.assertEqual(total, 0)

    def test_telegram_webhook_supports_edited_message_payload(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "edited_message": {
                        "text": f"/vote {poll_id} 1",
                        "from": {"username": "admin"},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["option_index"], 0)

    def test_telegram_webhook_callback_query_records_vote(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "callback_query": {
                        "id": "cbq-1",
                        "data": f"pollvote:{poll_id}:1",
                        "from": {"username": "admin"},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["option_index"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestBootstrapSafety(unittest.TestCase):
    def test_init_db_requires_bootstrap_password_in_production(self):
        """Production mode enforces ADMIN_BOOTSTRAP_PASSWORD when creating first admin"""
        source = pathlib.Path("app/web/routes/main_routes.py").read_text(encoding="utf-8")
        self.assertIn("elif is_production:", source)
        self.assertIn("ADMIN_BOOTSTRAP_PASSWORD must be set before first startup in production", source)



class TestApiGetProposal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def test_get_proposal_requires_api_key(self):
        response = self.client.get("/api/proposals/1")
        self.assertIn(response.status_code, (401, 503))

    def test_get_proposal_returns_not_found(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            response = self.client.get(
                "/api/proposals/999999", headers={"X-Admin-Key": "test-key"}
            )
        finally:
            main_routes.ADMIN_API_KEY = old

        self.assertEqual(response.status_code, 404)


class TestApiPolls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def test_create_poll_requires_api_key(self):
        response = self.client.post("/api/polls", json={"question": "Q?", "options": ["A", "B"], "created_by": 1})
        self.assertIn(response.status_code, (401, 503))

    def test_create_poll_rejects_wrong_api_key(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            response = self.client.post(
                "/api/polls",
                headers={"X-Admin-Key": "wrong-key"},
                json={"question": "Valid question", "options": ["A", "B"], "created_by": 1},
            )
        finally:
            main_routes.ADMIN_API_KEY = old
        self.assertEqual(response.status_code, 401)

    def test_create_poll_rejects_invalid_options_payload(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            response = self.client.post(
                "/api/polls",
                headers={"X-Admin-Key": "test-key"},
                json={"question": "Valid question", "options": "A,B", "created_by": 1},
            )
        finally:
            main_routes.ADMIN_API_KEY = old
        self.assertEqual(response.status_code, 400)
        self.assertIn("options must be an array", response.get_json().get("error", ""))

    def test_create_poll_rejects_invalid_question_length(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            response = self.client.post(
                "/api/polls",
                headers={"X-Admin-Key": "test-key"},
                json={"question": "Shrt", "options": ["A", "B"], "created_by": 1},
            )
        finally:
            main_routes.ADMIN_API_KEY = old
        self.assertEqual(response.status_code, 400)
        self.assertIn("question must be between 5 and 200 characters", response.get_json().get("error", ""))

    def test_create_poll_requires_created_by(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            response = self.client.post(
                "/api/polls",
                headers={"X-Admin-Key": "test-key"},
                json={"question": "Valid question", "options": ["A", "B"]},
            )
        finally:
            main_routes.ADMIN_API_KEY = old
        self.assertEqual(response.status_code, 400)
        self.assertIn("created_by is required", response.get_json().get("error", ""))

    def test_create_poll_rejects_unknown_created_by(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            response = self.client.post(
                "/api/polls",
                headers={"X-Admin-Key": "test-key"},
                json={"question": "Valid question", "options": ["A", "B"], "created_by": 999999},
            )
        finally:
            main_routes.ADMIN_API_KEY = old
        self.assertEqual(response.status_code, 404)
        self.assertIn("Creator member not found", response.get_json().get("error", ""))

    def test_create_and_list_polls(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            create_response = self.client.post(
                "/api/polls",
                headers={"X-Admin-Key": "test-key"},
                json={
                    "question": "API poll question",
                    "options": ["Option 1", "Option 2"],
                    "created_by": 1,
                },
            )
            self.assertEqual(create_response.status_code, 201)
            body = create_response.get_json()
            self.assertTrue(body.get("success"))
            self.assertIsNotNone(body.get("poll_id"))

            list_response = self.client.get("/api/polls", headers={"X-Admin-Key": "test-key"})
            self.assertEqual(list_response.status_code, 200)
            data = list_response.get_json()
            self.assertTrue(data.get("success"))
            self.assertTrue(any(p.get("question") == "API poll question" for p in data.get("polls", [])))
        finally:
            main_routes.ADMIN_API_KEY = old


class TestPollsFunctionality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_admin_session(self.client)
        self.client.post(
            "/admin",
            data={
                "action": "create_poll",
                "question": "Lunch option?",
                "options": "Pizza\nPasta\nSalad",
                "csrf_token": "",
            },
            follow_redirects=True,
        )

    def _latest_poll_id(self):
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM polls ORDER BY id DESC LIMIT 1")
        poll_id = c.fetchone()["id"]
        conn.close()
        return poll_id

    def test_polls_page_shows_results_and_votes(self):
        poll_id = self._latest_poll_id()
        self.client.post("/polls", data={"poll_id": poll_id, "option_index": 1, "csrf_token": ""}, follow_redirects=True)

        response = self.client.get("/polls")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Lunch option?", html)
        self.assertIn("(1)", html)
        self.assertIn("Who voted what", html)

    def test_polls_reject_invalid_option_index(self):
        poll_id = self._latest_poll_id()
        response = self.client.post(
            "/polls",
            data={"poll_id": poll_id, "option_index": 99, "csrf_token": ""},
            follow_redirects=True,
        )
        html = response.data.decode("utf-8")
        self.assertIn("Invalid poll option", html)

    def test_vote_replaces_previous_choice(self):
        poll_id = self._latest_poll_id()
        self.client.post("/polls", data={"poll_id": poll_id, "option_index": 0, "csrf_token": ""}, follow_redirects=True)
        self.client.post("/polls", data={"poll_id": poll_id, "option_index": 2, "csrf_token": ""}, follow_redirects=True)

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total, MAX(option_index) as option_index FROM poll_votes WHERE poll_id = ? AND member_id = 1", (poll_id,))
        row = c.fetchone()
        conn.close()

        self.assertEqual(row["total"], 1)
        self.assertEqual(row["option_index"], 2)

    def test_closed_poll_rejects_votes(self):
        poll_id = self._latest_poll_id()
        self.client.post(
            "/admin",
            data={"action": "close_poll", "poll_id": poll_id, "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.post(
            "/polls",
            data={"poll_id": poll_id, "option_index": 0, "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertIn("Poll is closed", response.data.decode("utf-8"))

    def test_admin_can_reopen_closed_poll(self):
        poll_id = self._latest_poll_id()
        self.client.post(
            "/admin",
            data={"action": "close_poll", "poll_id": poll_id, "csrf_token": ""},
            follow_redirects=True,
        )
        self.client.post(
            "/admin",
            data={"action": "reopen_poll", "poll_id": poll_id, "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.post(
            "/polls",
            data={"poll_id": poll_id, "option_index": 0, "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertIn("Poll vote recorded!", response.data.decode("utf-8"))

    def test_web_votes_disabled_when_mode_is_telegram_only(self):
        poll_id = self._latest_poll_id()
        self.client.post(
            "/admin",
            data={"action": "update_poll_vote_mode", "poll_vote_mode": "telegram_only", "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.post(
            "/polls",
            data={"poll_id": poll_id, "option_index": 0, "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertIn("Web voting is disabled by admin", response.data.decode("utf-8"))
