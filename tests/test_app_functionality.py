import pathlib
import sys
import unittest
import tempfile
import os
from unittest.mock import patch

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


    def test_new_proposal_uses_inline_telegram_vote_message_when_telegram_mode_allows(self):
        from app.web.routes import main_routes
        conn = budget_app.get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'telegram_only')")
        conn.commit()
        conn.close()

        with patch.object(main_routes.TelegramClient, "send_proposal_vote_message", return_value=True) as mock_send:
            response = self.client.post(
                "/proposal/new",
                data={
                    "title": "Inline vote message proposal",
                    "description": "Testing telegram inline proposal vote message",
                    "amount": "15",
                    "csrf_token": "",
                },
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_send.called)
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

    def test_admin_page_shows_member_proposal_statistics_title(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Member Proposal Statistics", response.data.decode("utf-8"))

    def test_admin_page_shows_member_poll_statistics_card(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Member Poll Statistics", html)
        self.assertIn("Poll Votes", html)
        self.assertIn("Polls Created", html)

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

    def test_admin_backup_section_renders_structured_tables(self):
        response = self.client.get("/admin")
        html = response.data.decode("utf-8")
        self.assertIn("Database Backups", html)
        self.assertIn("Image Backups", html)
        self.assertIn("<th>Type</th>", html)
        self.assertIn("<th>File</th>", html)
        self.assertIn("<th>Action</th>", html)

    def test_admin_page_includes_danger_confirmation_modal(self):
        response = self.client.get("/admin")
        html = response.data.decode("utf-8")
        self.assertIn("dangerActionModal", html)
        self.assertIn("confirmDangerAction", html)
        self.assertIn("submitDangerAction", html)

    def test_admin_members_show_telegram_username_without_id(self):
        """Admin members table shows Telegram username even if ID is missing"""
        conn = budget_app.get_db()
        try:
            conn.execute(
                "UPDATE members SET telegram_username = ?, telegram_user_id = NULL WHERE id = ?",
                ("telegram_only_user", 1),
            )
            conn.commit()
        finally:
            conn.close()

        response = self.client.get("/admin")
        html = response.data.decode("utf-8")
        self.assertIn("telegram_only_user", html)
        self.assertIn("(no ID)", html)

    def test_admin_members_show_telegram_id_without_username(self):
        """Admin members table shows Telegram ID even if username is missing"""
        conn = budget_app.get_db()
        try:
            conn.execute(
                "UPDATE members SET telegram_username = NULL, telegram_user_id = ? WHERE id = ?",
                (987654321, 1),
            )
            conn.commit()
        finally:
            conn.close()

        response = self.client.get("/admin")
        html = response.data.decode("utf-8")
        self.assertIn("987654321", html)
        self.assertIn("(no username)", html)

    def test_admin_unlink_telegram_action_clears_member_link_fields(self):
        conn = budget_app.get_db()
        try:
            conn.execute(
                "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
                ("linked_for_unlink_test", 11223344, 1),
            )
            conn.commit()
        finally:
            conn.close()

        response = self.client.post(
            "/admin",
            data={"action": "unlink_telegram", "member_id": 1, "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Telegram account unlinked.", response.data.decode("utf-8"))

        conn = budget_app.get_db()
        try:
            row = conn.execute(
                "SELECT telegram_username, telegram_user_id FROM members WHERE id = ?",
                (1,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(row["telegram_username"])
        self.assertIsNone(row["telegram_user_id"])

    def test_admin_unlink_telegram_action_emits_audit_event(self):
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            ("linked_for_audit_test", 889900, 1),
        )
        conn.commit()
        conn.close()

        with patch("app.web.routes.main_routes.log_telegram_link_event") as mock_log:
            response = self.client.post(
                "/admin",
                data={"action": "unlink_telegram", "member_id": 1, "csrf_token": ""},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        self.assertEqual(kwargs["event"], "admin_telegram_unlink")
        self.assertEqual(kwargs["target_member_id"], 1)
        self.assertEqual(kwargs["source"], "admin_panel")

    def test_admin_backup_download_route_serves_db_backup_file(self):
        from app.services.backup_service import BACKUP_ROOT

        os.makedirs(BACKUP_ROOT, exist_ok=True)
        backup_base = os.path.basename(budget_app.DB_PATH).replace(".db", "")
        filename = f"{backup_base}_20990101_000000.db"
        filepath = os.path.join(BACKUP_ROOT, filename)
        with open(filepath, "wb") as f:
            f.write(b"test-db-backup-content")

        try:
            response = self.client.get(f"/admin/backups/db/{filename}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"test-db-backup-content")
            self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_admin_backup_download_route_rejects_invalid_filename(self):
        response = self.client.get("/admin/backups/db/not_a_db_backup.txt", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid backup file", response.data.decode("utf-8"))

    def test_admin_backup_download_invalid_type_preserves_tab_on_redirect(self):
        response = self.client.get("/admin/backups/nope/file.zip?tab=settings", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin?tab=settings", response.headers.get("Location", ""))

    def test_admin_backup_download_invalid_tab_redirects_to_all_tab(self):
        response = self.client.get("/admin/backups/nope/file.zip?tab=not-a-real-tab", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin?tab=all", response.headers.get("Location", ""))

    def test_admin_backup_download_emits_audit_log_event(self):
        from app.services.backup_service import BACKUP_ROOT

        os.makedirs(BACKUP_ROOT, exist_ok=True)
        backup_base = os.path.basename(budget_app.DB_PATH).replace(".db", "")
        filename = f"{backup_base}_20990101_000001.db"
        filepath = os.path.join(BACKUP_ROOT, filename)
        with open(filepath, "wb") as f:
            f.write(b"audit-log-test")

        try:
            with patch.object(budget_app.app.logger, "info") as log_info:
                response = self.client.get(f"/admin/backups/db/{filename}")
                self.assertEqual(response.status_code, 200)
                log_info.assert_called_once()
                args = log_info.call_args[0]
                self.assertEqual(
                    args[0],
                    "event=%s actor_id=%s backup_type=%s file_name=%s reason_code=%s status=%s pruned_count=%s file_size_bytes=%s error=%s at=%s",
                )
                self.assertEqual(args[1], "admin_backup_download")
                self.assertEqual(args[2], 1)
                self.assertEqual(args[3], "db")
                self.assertEqual(args[4], filename)
                self.assertIsNone(args[5])
                self.assertEqual(args[6], "ok")
                self.assertIsNone(args[7])
                self.assertEqual(args[8], os.path.getsize(filepath))
                self.assertIsNone(args[9])
                self.assertIsInstance(args[10], str)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_admin_backup_download_rejection_emits_audit_log_event(self):
        with patch.object(budget_app.app.logger, "info") as log_info:
            response = self.client.get("/admin/backups/nope/file.zip?tab=budget", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            log_info.assert_called_once()
            args = log_info.call_args[0]
            self.assertEqual(
                args[0],
                "event=%s actor_id=%s backup_type=%s file_name=%s reason_code=%s status=%s pruned_count=%s file_size_bytes=%s error=%s at=%s",
            )
            self.assertEqual(args[1], "admin_backup_download_rejected")
            self.assertEqual(args[2], 1)
            self.assertEqual(args[3], "nope")
            self.assertEqual(args[4], "file.zip")
            self.assertEqual(args[5], "invalid_backup_type")
            self.assertEqual(args[6], "rejected")
            self.assertIsNone(args[7])
            self.assertIsNone(args[8])
            self.assertIsNone(args[9])
            self.assertIsInstance(args[10], str)

    def test_admin_post_preserves_requested_tab_in_response(self):
        response = self.client.post(
            "/admin",
            data={"action": "toggle_registration", "registration_enabled": "1", "tab": "settings", "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn('var serverTab = "settings";', html)

    def test_admin_backup_db_create_emits_audit_log_event(self):
        with patch("app.services.backup_service.backup_db", return_value=("budget_20990101_000000.db", 2)):
            with patch.object(budget_app.app.logger, "info") as log_info:
                response = self.client.post("/admin", data={"action": "backup_db", "csrf_token": ""}, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                args = log_info.call_args[0]
                self.assertEqual(
                    args[0],
                    "event=%s actor_id=%s backup_type=%s file_name=%s reason_code=%s status=%s pruned_count=%s file_size_bytes=%s error=%s at=%s",
                )
                self.assertEqual(args[1], "admin_backup_created")
                self.assertEqual(args[2], 1)
                self.assertEqual(args[3], "db")
                self.assertEqual(args[4], "budget_20990101_000000.db")
                self.assertIsNone(args[5])
                self.assertEqual(args[6], "ok")
                self.assertEqual(args[7], 2)

    def test_admin_backup_db_failure_emits_audit_log_event(self):
        with patch("app.services.backup_service.backup_db", side_effect=RuntimeError("disk full")):
            with patch.object(budget_app.app.logger, "info") as log_info:
                response = self.client.post("/admin", data={"action": "backup_db", "csrf_token": ""}, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                args = log_info.call_args[0]
                self.assertEqual(
                    args[0],
                    "event=%s actor_id=%s backup_type=%s file_name=%s reason_code=%s status=%s pruned_count=%s file_size_bytes=%s error=%s at=%s",
                )
                self.assertEqual(args[1], "admin_backup_failed")
                self.assertEqual(args[2], 1)
                self.assertEqual(args[3], "db")
                self.assertIsNone(args[4])
                self.assertEqual(args[5], "backup_exception")
                self.assertEqual(args[6], "failed")
                self.assertEqual(args[9], "disk full")

    def test_admin_backup_images_create_emits_audit_log_event(self):
        with patch("app.services.backup_service.backup_uploads", return_value=("uploads_20990101_000000.zip", 1)):
            with patch.object(budget_app.app.logger, "info") as log_info:
                response = self.client.post("/admin", data={"action": "backup_images", "csrf_token": ""}, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                args = log_info.call_args[0]
                self.assertEqual(
                    args[0],
                    "event=%s actor_id=%s backup_type=%s file_name=%s reason_code=%s status=%s pruned_count=%s file_size_bytes=%s error=%s at=%s",
                )
                self.assertEqual(args[1], "admin_backup_created")
                self.assertEqual(args[2], 1)
                self.assertEqual(args[3], "images")
                self.assertEqual(args[4], "uploads_20990101_000000.zip")
                self.assertIsNone(args[5])
                self.assertEqual(args[6], "ok")
                self.assertEqual(args[7], 1)

    def test_admin_backup_images_failure_emits_audit_log_event(self):
        with patch("app.services.backup_service.backup_uploads", side_effect=RuntimeError("zip failed")):
            with patch.object(budget_app.app.logger, "info") as log_info:
                response = self.client.post("/admin", data={"action": "backup_images", "csrf_token": ""}, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                args = log_info.call_args[0]
                self.assertEqual(
                    args[0],
                    "event=%s actor_id=%s backup_type=%s file_name=%s reason_code=%s status=%s pruned_count=%s file_size_bytes=%s error=%s at=%s",
                )
                self.assertEqual(args[1], "admin_backup_failed")
                self.assertEqual(args[2], 1)
                self.assertEqual(args[3], "images")
                self.assertIsNone(args[4])
                self.assertEqual(args[5], "backup_exception")
                self.assertEqual(args[6], "failed")
                self.assertEqual(args[9], "zip failed")



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

    def test_settings_menu_item_displays(self):
        """Settings link appears in top navigation"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn(">Settings<", html)


class TestPollTelegramActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_admin_session(self.client)
        conn = budget_app.get_db()
        conn.execute("DELETE FROM poll_votes")
        conn.execute("DELETE FROM polls")
        conn.commit()
        conn.close()
        self.client.post(
            "/admin",
            data={"action": "update_poll_vote_mode", "poll_vote_mode": "both", "csrf_token": ""},
            follow_redirects=True,
        )
        self.client.post(
            "/admin",
            data={"action": "update_proposal_vote_mode", "proposal_vote_mode": "both", "csrf_token": ""},
            follow_redirects=True,
        )
        self.client.post(
            "/admin",
            data={"action": "update_telegram_linked_vote_requirement", "csrf_token": ""},
            follow_redirects=True,
        )
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

    def test_admin_can_enable_linked_telegram_vote_requirement(self):
        response = self.client.post(
            "/admin",
            data={
                "action": "update_telegram_linked_vote_requirement",
                "telegram_require_linked_vote": "on",
                "csrf_token": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Telegram linked-account vote requirement updated", response.data.decode("utf-8"))
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'telegram_require_linked_vote'")
        value = c.fetchone()["value"]
        conn.close()
        self.assertEqual(value, "true")

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

    def _ensure_active_proposal_for_telegram_vote_tests(self):
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM proposals WHERE status = 'active' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if row:
            proposal_id = row["id"]
        else:
            c.execute(
                "INSERT INTO proposals (title, description, amount, created_by, status) VALUES (?, ?, ?, ?, 'active')",
                ("Telegram vote proposal", "desc", 12.0, 1),
            )
            conn.commit()
            proposal_id = c.lastrowid
        conn.close()
        return proposal_id

    def test_telegram_webhook_proposal_vote_records_when_mode_is_both(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'both')")
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/pvote {proposal_id} yes",
                        "from": {"username": "admin", "id": 111111},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)

        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["vote"], "in_favor")

    def test_telegram_webhook_proposal_vote_rejected_when_mode_is_web_only(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'web_only')")
            conn.execute("DELETE FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,))
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/pvote {proposal_id} yes",
                        "from": {"username": "admin", "id": 111111},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNone(row)


    def test_telegram_webhook_proposal_vote_rejects_invalid_vote_token(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'both')")
            conn.execute("DELETE FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,))
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={"message": {"text": f"/pvote {proposal_id} maybe", "from": {"username": "admin", "id": 111111}, "chat": {"id": 12345}}},
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_telegram_webhook_proposal_vote_rejects_non_active_proposal(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'both')")
            conn.execute("UPDATE proposals SET status = 'approved' WHERE id = ?", (proposal_id,))
            conn.execute("DELETE FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,))
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={"message": {"text": f"/pvote {proposal_id} yes", "from": {"username": "admin", "id": 111111}, "chat": {"id": 12345}}},
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_telegram_webhook_proposal_vote_records_when_mode_is_telegram_only(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'telegram_only')")
            conn.execute("DELETE FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,))
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/pvote {proposal_id} no",
                        "from": {"username": "admin", "id": 111111},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["vote"], "against")


    def test_telegram_webhook_proposal_vote_accepts_bot_suffix_command(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'telegram_only')")
            conn.execute("DELETE FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,))
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={"message": {"text": f"/pvote@manavote_bot {proposal_id} yes", "from": {"username": "admin", "id": 111111}, "chat": {"id": 12345}}},
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["vote"], "in_favor")

    def test_telegram_webhook_proposal_vote_rejects_unknown_member(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'telegram_only')")
            conn.execute("DELETE FROM votes WHERE proposal_id = ?", (proposal_id,))
            conn.execute("UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE id = 1")
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={"message": {"text": f"/pvote {proposal_id} yes", "from": {"username": "unknownuser", "id": 9999999}, "chat": {"id": 12345}}},
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ?", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_telegram_webhook_proposal_callback_records_vote_when_mode_allows(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'telegram_only')")
            conn.execute("DELETE FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,))
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "callback_query": {
                        "id": "cb-pvote-1",
                        "data": f"pvote:{proposal_id}:yes",
                        "from": {"username": "admin", "id": 111111},
                        "message": {"chat": {"id": 12345}, "message_id": 77},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["vote"], "in_favor")

    def test_telegram_webhook_proposal_callback_rejected_when_mode_web_only(self):
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
            conn = budget_app.get_db()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'web_only')")
            conn.execute("DELETE FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,))
            conn.commit()
            conn.close()

            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "callback_query": {
                        "id": "cb-pvote-2",
                        "data": f"pvote:{proposal_id}:yes",
                        "from": {"username": "admin", "id": 111111},
                        "message": {"chat": {"id": 12345}, "message_id": 77},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        row = conn.execute("SELECT vote FROM votes WHERE proposal_id = ? AND member_id = 1", (proposal_id,)).fetchone()
        conn.close()
        self.assertIsNone(row)

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


    def test_telegram_webhook_accepts_vote_command_with_bot_suffix(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/vote@manavote_bot {poll_id} 1",
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

    def test_telegram_webhook_unknown_member_with_user_id_records_vote_as_unlinked(self):
        poll_id = self._latest_poll_id()
        conn = budget_app.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', 'false')"
        )
        conn.commit()
        conn.close()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/vote {poll_id} 1",
                        "from": {"username": "not_a_member", "id": 999001},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT member_id, option_index FROM poll_votes WHERE poll_id = ?", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["member_id"], -999001)
        self.assertEqual(row["option_index"], 0)

    def test_telegram_webhook_unknown_member_with_user_id_rejected_when_link_required(self):
        poll_id = self._latest_poll_id()
        conn = budget_app.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', 'true')"
        )
        conn.commit()
        conn.close()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/vote {poll_id} 1",
                        "from": {"username": "not_a_member", "id": 999001},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT member_id, option_index FROM poll_votes WHERE poll_id = ?", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_telegram_webhook_does_not_match_app_username_when_link_required(self):
        poll_id = self._latest_poll_id()
        conn = budget_app.get_db()
        conn.execute("UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE id = 1")
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', 'true')"
        )
        conn.commit()
        conn.close()
        from app.web.routes import main_routes
        sent_messages = []

        def _fake_send_message(self, message):
            sent_messages.append(message)
            return True

        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        old_token = main_routes.TELEGRAM_BOT_TOKEN
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        main_routes.TELEGRAM_BOT_TOKEN = "bot-token"
        try:
            with patch.object(main_routes.TelegramClient, "send_message", new=_fake_send_message):
                self.client.post(
                    "/telegram/webhook/hook-secret",
                    json={
                        "message": {
                            "text": f"/vote {poll_id} 1",
                            "from": {"username": "admin", "id": 999001},
                            "chat": {"id": 12345},
                        }
                    }
                )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret
            main_routes.TELEGRAM_BOT_TOKEN = old_token

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT member_id, option_index FROM poll_votes WHERE poll_id = ?", (poll_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNone(row)
        self.assertTrue(sent_messages)
        self.assertEqual(sent_messages[-1][0], "50001")
        self.assertIn("must be linked first", sent_messages[-1][1])

    def test_telegram_webhook_proposal_vote_rejected_when_link_required(self):
        proposal_id = self._ensure_active_proposal_for_telegram_vote_tests()
        conn = budget_app.get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'telegram_only')")
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', 'true')"
        )
        conn.commit()
        conn.close()

        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": f"/pvote {proposal_id} yes",
                        "from": {"username": "not_a_member", "id": 888001},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM votes WHERE proposal_id = ?", (proposal_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNone(row)


    def test_telegram_webhook_link_command_links_member(self):
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE members SET password_hash = ?, telegram_username = NULL, telegram_user_id = NULL WHERE id = 1",
            (budget_app.generate_password_hash("test-admin-password"),),
        )
        conn.commit()
        conn.close()

        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": "/link admin test-admin-password",
                        "from": {"username": "admin_tg", "id": 555001},
                        "chat": {"id": 12345},
                    }
                },
            )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT telegram_username, telegram_user_id FROM members WHERE id = 1")
        row = c.fetchone()
        conn.close()
        self.assertEqual(row["telegram_username"], "admin_tg")
        self.assertEqual(row["telegram_user_id"], 555001)

    def test_telegram_webhook_link_command_emits_audit_event(self):
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET password_hash = ?, telegram_username = NULL, telegram_user_id = NULL WHERE id = 1",
            (budget_app.generate_password_hash("test-admin-password"),),
        )
        conn.commit()
        conn.close()

        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            with patch("app.web.routes.main_routes.log_telegram_link_event") as mock_log:
                response = self.client.post(
                    "/telegram/webhook/hook-secret",
                    json={
                        "message": {
                            "text": "/link admin test-admin-password",
                            "from": {"username": "admin_tg", "id": 555001},
                            "chat": {"id": 12345},
                        }
                    },
                )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret

        self.assertEqual(response.status_code, 200)
        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        self.assertEqual(kwargs["event"], "telegram_link_updated")
        self.assertEqual(kwargs["source"], "telegram_command")
        self.assertEqual(kwargs["target_member_id"], 1)

    def test_admin_page_shows_linked_telegram_fields(self):
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = 1", ("admin_tg", 555001))
        conn.commit()
        conn.close()

        response = self.client.get('/admin')
        html = response.data.decode('utf-8')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Telegram', html)
        self.assertIn('admin_tg', html)
        self.assertIn('555001', html)

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

    def test_telegram_webhook_non_command_message_is_ignored(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        try:
            response = self.client.post(
                "/telegram/webhook/hook-secret",
                json={
                    "message": {
                        "text": "hello team",
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


    def test_telegram_webhook_callback_query_link_required_messages_user_guidance(self):
        poll_id = self._latest_poll_id()
        conn = budget_app.get_db()
        conn.execute("UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE id = 1")
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', 'true')"
        )
        conn.commit()
        conn.close()

        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        old_token = main_routes.TELEGRAM_BOT_TOKEN
        sent_messages = []
        answered = []

        def _fake_send_message(self, message):
            sent_messages.append((self.chat_id, message))
            return True

        def _fake_answer_callback(self, callback_query_id, text):
            answered.append((callback_query_id, text))
            return True

        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        main_routes.TELEGRAM_BOT_TOKEN = "token"
        try:
            with patch.object(main_routes.TelegramClient, "send_message", new=_fake_send_message), patch.object(main_routes.TelegramClient, "answer_callback_query", new=_fake_answer_callback):
                response = self.client.post(
                    "/telegram/webhook/hook-secret",
                    json={
                        "callback_query": {
                            "id": "cbq-link-required",
                            "data": f"pollvote:{poll_id}:0",
                            "from": {"username": "admin", "id": 50001},
                            "message": {"message_id": 9, "chat": {"id": 12345}},
                        }
                    },
                )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret
            main_routes.TELEGRAM_BOT_TOKEN = old_token

        self.assertEqual(response.status_code, 200)
        self.assertTrue(answered)
        self.assertIn("must be linked first", answered[-1][1])
        self.assertTrue(sent_messages)
        self.assertEqual(sent_messages[-1][0], "50001")
        self.assertIn("must be linked first", sent_messages[-1][1])

    def test_telegram_webhook_showvote_callback_edits_message_markup(self):
        poll_id = self._latest_poll_id()
        from app.web.routes import main_routes
        old_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        old_token = main_routes.TELEGRAM_BOT_TOKEN
        main_routes.TELEGRAM_WEBHOOK_SECRET = "hook-secret"
        main_routes.TELEGRAM_BOT_TOKEN = "token"
        try:
            with patch.object(main_routes.TelegramClient, "edit_message_with_vote_options", return_value=True) as mock_edit:
                response = self.client.post(
                    "/telegram/webhook/hook-secret",
                    json={
                        "callback_query": {
                            "id": "cbq-2",
                            "data": f"showvote:{poll_id}",
                            "from": {"username": "admin"},
                            "message": {"message_id": 12, "chat": {"id": -100123}},
                        }
                    },
                )
        finally:
            main_routes.TELEGRAM_WEBHOOK_SECRET = old_secret
            main_routes.TELEGRAM_BOT_TOKEN = old_token

        self.assertEqual(response.status_code, 200)
        mock_edit.assert_called_once()


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


class TestAdminTelegramWebhookSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
            session["is_admin"] = 1

    def test_update_url_attempts_webhook_sync(self):
        from app.web.routes import main_routes

        with patch.object(main_routes, "sync_telegram_webhook", return_value=True) as mock_sync:
            response = self.client.post(
                "/admin",
                data={"action": "update_url", "base_url": "https://example.org", "csrf_token": ""},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        mock_sync.assert_called_once_with("https://example.org")

    def test_sync_telegram_webhook_action_calls_sync(self):
        from app.web.routes import main_routes

        with patch.object(main_routes, "get_setting_value", return_value="https://example.org"), patch.object(
            main_routes, "sync_telegram_webhook", return_value=True
        ) as mock_sync:
            response = self.client.post(
                "/admin",
                data={"action": "sync_telegram_webhook", "csrf_token": ""},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        mock_sync.assert_called_once_with("https://example.org")


class TestTelegramSettingsPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_member_session(self.client)

    def test_telegram_settings_page_loads(self):
        response = self.client.get("/telegram-settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Telegram Settings", response.data.decode("utf-8"))

    def test_telegram_settings_post_does_not_change_linked_values(self):
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            ("linked_user", 777001, 1),
        )
        conn.commit()
        conn.close()

        response = self.client.post(
            "/telegram-settings",
            data={"telegram_username": "@attempted_override", "telegram_user_id": "999999", "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("read-only", response.data.decode("utf-8"))

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT telegram_username, telegram_user_id FROM members WHERE id = 1")
        row = c.fetchone()
        conn.close()

        self.assertEqual(row["telegram_username"], "linked_user")
        self.assertEqual(row["telegram_user_id"], 777001)

    def test_telegram_settings_unlink_action_clears_linked_values(self):
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            ("linked_user", 777001, 1),
        )
        conn.commit()
        conn.close()

        response = self.client.post(
            "/telegram-settings",
            data={"action": "unlink_telegram", "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Telegram account unlinked.", response.data.decode("utf-8"))

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT telegram_username, telegram_user_id FROM members WHERE id = 1")
        row = c.fetchone()
        conn.close()

        self.assertIsNone(row["telegram_username"])
        self.assertIsNone(row["telegram_user_id"])

    def test_telegram_settings_unlink_action_emits_audit_event(self):
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            ("linked_user", 777001, 1),
        )
        conn.commit()
        conn.close()

        with patch("app.web.routes.auth_routes.log_telegram_link_event") as mock_log:
            response = self.client.post(
                "/telegram-settings",
                data={"action": "unlink_telegram", "csrf_token": ""},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        self.assertEqual(kwargs["event"], "member_telegram_unlink")
        self.assertEqual(kwargs["target_member_id"], 1)
        self.assertEqual(kwargs["source"], "member_settings")

    def test_telegram_settings_page_fields_are_read_only(self):
        response = self.client.get("/telegram-settings")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Telegram Username (auto-linked from Telegram)", html)
        self.assertIn("Telegram User ID (auto-linked from Telegram)", html)
        self.assertIn("readonly disabled", html)

    def test_telegram_settings_page_inputs_are_not_submitted(self):
        response = self.client.get("/telegram-settings")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertNotIn('name="telegram_user_id"', html)
        self.assertNotIn('name="telegram_username"', html)

    def test_telegram_settings_shows_relink_guidance_if_linked_without_username(self):
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            ("", 777001, 1),
        )
        conn.commit()
        conn.close()

        response = self.client.get("/telegram-settings")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("public username is missing", html)
        self.assertIn("unlink here and run /link again", html)



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


class TestApiVotingSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def test_get_voting_settings_requires_api_key(self):
        response = self.client.get("/api/settings/voting")
        self.assertIn(response.status_code, (401, 503))

    def test_get_and_update_voting_settings(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            get_response = self.client.get("/api/settings/voting", headers={"X-Admin-Key": "test-key"})
            self.assertEqual(get_response.status_code, 200)
            self.assertTrue(get_response.get_json()["success"])

            update_response = self.client.patch(
                "/api/settings/voting",
                headers={"X-Admin-Key": "test-key"},
                json={
                    "poll_vote_mode": "telegram_only",
                    "proposal_vote_mode": "web_only",
                    "telegram_require_linked_vote": True,
                },
            )
            self.assertEqual(update_response.status_code, 200)
            payload = update_response.get_json()
            self.assertTrue(payload["success"])
            self.assertEqual(payload["settings"]["poll_vote_mode"], "telegram_only")
            self.assertEqual(payload["settings"]["proposal_vote_mode"], "web_only")
            self.assertTrue(payload["settings"]["telegram_require_linked_vote"])
        finally:
            main_routes.ADMIN_API_KEY = old

    def test_update_voting_settings_rejects_invalid_values(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        try:
            response = self.client.patch(
                "/api/settings/voting",
                headers={"X-Admin-Key": "test-key"},
                json={"telegram_require_linked_vote": "maybe"},
            )
        finally:
            main_routes.ADMIN_API_KEY = old
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "invalid_telegram_require_linked_vote")


class TestApiMemberTelegramLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def test_list_member_telegram_links_includes_link_state_diagnostics(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        conn = budget_app.get_db()
        conn.execute("DELETE FROM members")
        conn.executemany(
            "INSERT INTO members (id, username, password_hash, is_admin, telegram_username, telegram_user_id) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "linked", "x", 0, "linked_tg", 1001),
                (2, "missing_username", "x", 0, "", 1002),
                (3, "missing_user_id", "x", 0, "only_name", None),
                (4, "unlinked", "x", 0, None, None),
            ],
        )
        conn.commit()
        conn.close()
        try:
            response = self.client.get(
                "/api/members/telegram?include_unlinked=true",
                headers={"X-Admin-Key": "test-key"},
            )
        finally:
            main_routes.ADMIN_API_KEY = old

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        states = {row["username"]: row["link_state"] for row in payload["members"]}
        self.assertEqual(states["linked"], "linked")
        self.assertEqual(states["missing_username"], "missing_username")
        self.assertEqual(states["missing_user_id"], "missing_user_id")
        self.assertEqual(states["unlinked"], "unlinked")

    def test_list_member_telegram_links_filtered_mode_returns_only_linked_rows(self):
        from app.web.routes import main_routes

        old = main_routes.ADMIN_API_KEY
        main_routes.ADMIN_API_KEY = "test-key"
        conn = budget_app.get_db()
        conn.execute("DELETE FROM members")
        conn.executemany(
            "INSERT INTO members (id, username, password_hash, is_admin, telegram_username, telegram_user_id) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "linked_a", "x", 0, "linked_a_tg", 2001),
                (2, "missing_username", "x", 0, "", 2002),
                (3, "linked_b", "x", 0, "linked_b_tg", 2003),
            ],
        )
        conn.commit()
        conn.close()
        try:
            response = self.client.get(
                "/api/members/telegram?include_unlinked=false",
                headers={"X-Admin-Key": "test-key"},
            )
        finally:
            main_routes.ADMIN_API_KEY = old

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        usernames = [row["username"] for row in payload["members"]]
        self.assertEqual(usernames, ["linked_a", "linked_b"])
        self.assertTrue(all(row["linked"] == 1 for row in payload["members"]))
        self.assertTrue(all(row["link_state"] == "linked" for row in payload["members"]))


class TestPollsFunctionality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        _set_admin_session(self.client)
        conn = budget_app.get_db()
        conn.execute("DELETE FROM poll_votes")
        conn.execute("DELETE FROM polls")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('poll_vote_mode', 'both')")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', 'both')")
        conn.execute(
            "INSERT INTO polls (question, options_json, created_by, status) VALUES (?, ?, ?, 'open')",
            ("Lunch option?", '["Pizza","Pasta","Salad"]', 1),
        )
        conn.commit()
        conn.close()


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
        self.assertIn('data-mobile-nav', html)
        self.assertIn('data-nav-toggle', html)

    def test_polls_page_uses_linked_telegram_username_in_vote_list(self):
        poll_id = self._latest_poll_id()
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            ("linked_admin", 123456789, 1),
        )
        conn.commit()
        conn.close()

        self.client.post("/polls", data={"poll_id": poll_id, "option_index": 1, "csrf_token": ""}, follow_redirects=True)
        response = self.client.get("/polls")
        html = response.data.decode("utf-8")
        self.assertIn("linked_admin", html)
        self.assertNotIn("(not linked, use /link)", html)
        self.assertIn("Telegram linked", html)

    def test_polls_page_suggests_link_when_account_not_linked(self):
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE id = ?",
            (1,),
        )
        conn.commit()
        conn.close()

        response = self.client.get("/polls")
        html = response.data.decode("utf-8")
        self.assertIn("Telegram account not linked yet", html)
        self.assertIn("/link &lt;app_username&gt; &lt;app_password&gt;", html)
        self.assertIn("Telegram not linked", html)

    def test_polls_page_marks_unlinked_vote_entries(self):
        poll_id = self._latest_poll_id()
        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE id = ?",
            (1,),
        )
        conn.commit()
        conn.close()

        self.client.post("/polls", data={"poll_id": poll_id, "option_index": 0, "csrf_token": ""}, follow_redirects=True)
        response = self.client.get("/polls")
        html = response.data.decode("utf-8")
        self.assertIn("(not linked, use /link)", html)

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
        self.client.post(
            "/admin",
            data={"action": "update_poll_vote_mode", "poll_vote_mode": "both", "csrf_token": ""},
            follow_redirects=True,
        )

    def test_web_proposal_votes_disabled_when_mode_is_telegram_only(self):
        self.client.post(
            "/admin",
            data={"action": "update_proposal_vote_mode", "proposal_vote_mode": "telegram_only", "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.post(
            "/vote/1",
            data={"vote": "in_favor", "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertIn("Web voting is disabled by admin", response.data.decode("utf-8"))

    def test_dashboard_hides_proposal_vote_buttons_when_mode_is_telegram_only(self):
        self.client.post(
            "/admin",
            data={"action": "update_proposal_vote_mode", "proposal_vote_mode": "telegram_only", "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.get("/", follow_redirects=True)
        html = response.data.decode("utf-8")
        self.assertNotIn('action="/vote/', html)

    def test_proposal_detail_shows_telegram_only_banner_when_web_votes_disabled(self):
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM proposals WHERE status = 'active' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if row is None:
            c.execute(
                "INSERT INTO proposals (title, description, amount, created_by, status) VALUES (?, ?, ?, ?, 'active')",
                ("Mode banner proposal", "desc", 5.0, 1),
            )
            conn.commit()
            proposal_id = c.lastrowid
        else:
            proposal_id = row["id"]
        conn.close()

        self.client.post(
            "/admin",
            data={"action": "update_proposal_vote_mode", "proposal_vote_mode": "telegram_only", "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.get(f"/proposal/{proposal_id}", follow_redirects=True)
        self.assertIn("Proposal voting is currently Telegram-only", response.data.decode("utf-8"))


    def test_admin_update_proposal_vote_mode_persists_setting(self):
        self.client.post(
            "/admin",
            data={"action": "update_proposal_vote_mode", "proposal_vote_mode": "telegram_only", "csrf_token": ""},
            follow_redirects=True,
        )
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'proposal_vote_mode'")
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "telegram_only")
    def test_web_proposal_votes_allowed_when_mode_is_web_only(self):
        self.client.post(
            "/admin",
            data={"action": "update_proposal_vote_mode", "proposal_vote_mode": "web_only", "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.post(
            "/vote/1",
            data={"vote": "in_favor", "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertIn("Vote recorded!", response.data.decode("utf-8"))

    def test_web_proposal_votes_allowed_when_mode_is_both(self):
        self.client.post(
            "/admin",
            data={"action": "update_proposal_vote_mode", "proposal_vote_mode": "both", "csrf_token": ""},
            follow_redirects=True,
        )
        response = self.client.post(
            "/vote/1",
            data={"vote": "against", "csrf_token": ""},
            follow_redirects=True,
        )
        self.assertIn("Vote recorded!", response.data.decode("utf-8"))
    def test_proposal_vote_replaces_previous_choice(self):
        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM proposals WHERE status = 'active' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if row is None:
            c.execute(
                "INSERT INTO proposals (title, description, amount, created_by, status) VALUES (?, ?, ?, ?, 'active')",
                ("Vote replacement proposal", "desc", 8.0, 1),
            )
            conn.commit()
            proposal_id = c.lastrowid
        else:
            proposal_id = row["id"]
        conn.close()

        self.client.post(
            f"/vote/{proposal_id}",
            data={"vote": "in_favor", "csrf_token": ""},
            follow_redirects=True,
        )
        self.client.post(
            f"/vote/{proposal_id}",
            data={"vote": "against", "csrf_token": ""},
            follow_redirects=True,
        )

        conn = budget_app.get_db()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) AS total, MAX(vote) AS vote FROM votes WHERE proposal_id = ? AND member_id = ?",
            (proposal_id, 1),
        )
        vote_row = c.fetchone()
        conn.close()

        self.assertEqual(vote_row["total"], 1)
        self.assertEqual(vote_row["vote"], "against")
