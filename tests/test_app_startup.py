import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import app
from app.startup import check_auto_backup, check_telegram_group_configuration, run_startup_steps


class TestAppStartup(unittest.TestCase):
    def test_warns_when_telegram_group_has_no_bot_username(self):
        environment = {
            "TELEGRAM_CHAT_ID": "-1001234567890",
            "TELEGRAM_BOT_USERNAME": "",
        }
        with patch("app.startup.logging.getLogger") as get_logger:
            reason = check_telegram_group_configuration(environ=environment)

        self.assertEqual(reason, "missing_bot_username_for_group")
        warning = get_logger.return_value.warning
        warning.assert_called_once()
        self.assertIn("reason_code=%s", warning.call_args.args[0])
        self.assertEqual(warning.call_args.args[1], "missing_bot_username_for_group")

    def test_does_not_warn_for_private_chat_or_configured_group(self):
        configurations = (
            {"TELEGRAM_CHAT_ID": "123456789", "TELEGRAM_BOT_USERNAME": ""},
            {"TELEGRAM_CHAT_ID": "-1001234567890", "TELEGRAM_BOT_USERNAME": "ManaVoteBot"},
        )
        for environment in configurations:
            logger = Mock()
            reason = check_telegram_group_configuration(logger=logger, environ=environment)
            self.assertIsNone(reason)
            logger.warning.assert_not_called()

    def test_warns_for_forum_thread_even_without_negative_chat_id(self):
        logger = Mock()
        reason = check_telegram_group_configuration(
            logger=logger,
            environ={"TELEGRAM_THREAD_ID": "42"},
        )
        self.assertEqual(reason, "missing_bot_username_for_group")
        logger.warning.assert_called_once()

    def test_create_app_fails_fast_on_db_initialization_error(self):
        with patch("app.run_startup_steps", side_effect=sqlite3.OperationalError("boom")):
            with self.assertRaises(RuntimeError):
                app.create_app()

    def test_run_startup_steps_executes_in_order(self):
        events = []
        with patch("app.startup.ensure_db_ready", side_effect=lambda: events.append("db")),              patch("app.startup.check_auto_backup", side_effect=lambda *a, **kw: events.append("backup")),              patch("app.startup.start_scheduler", side_effect=lambda *_: events.append("scheduler")):
            run_startup_steps(app.flask_app, "test.db", "uploads")
        self.assertEqual(events, ["db", "scheduler", "backup"])

    def test_scheduler_failure_is_warning_not_fatal(self):
        with patch("app.startup.ensure_db_ready"),              patch("app.startup.check_auto_backup"),              patch("app.startup.start_scheduler", side_effect=OSError("nope")),              patch("app.logging.warning") as warning_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads")
        warning_mock.assert_called()

    def test_auto_backup_failure_is_warning_not_fatal(self):
        with patch("app.startup.ensure_db_ready"),              patch("app.startup.start_scheduler"),              patch("app.startup.check_auto_backup", side_effect=ValueError("bad backup state")),              patch("app.logging.warning") as warning_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads")
        warning_mock.assert_called()

    def test_create_app_logs_warning_on_optional_import_error(self):
        with patch("app.run_startup_steps", side_effect=ImportError("optional dep missing")),              patch("app.logging.warning") as warning_mock:
            created_app = app.create_app()

        self.assertIs(created_app, app.flask_app)
        warning_mock.assert_called()

    def test_test_env_skips_scheduler_and_auto_backup(self):
        with patch("app.startup.ensure_db_ready"),              patch("app.startup.start_scheduler") as scheduler_mock,              patch("app.startup.check_auto_backup") as backup_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads", app_env="test")
        scheduler_mock.assert_not_called()
        backup_mock.assert_not_called()

    def test_startup_summary_logs_ready_status(self):
        with patch("app.startup.ensure_db_ready"),              patch("app.startup.start_scheduler"),              patch("app.startup.check_auto_backup"),              patch("app.startup.logging.info") as info_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads", app_env="test")

        message = info_mock.call_args[0][1]
        self.assertIn('"mode": "test"', message)
        self.assertIn('"status": "ready"', message)

    def test_startup_summary_logs_degraded_reason_codes(self):
        with patch("app.startup.ensure_db_ready"),              patch("app.startup.start_scheduler", side_effect=OSError("scheduler down")),              patch("app.startup.check_auto_backup", side_effect=ValueError("backup broken")),              patch("app.startup.logging.info") as info_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads", app_env="development")

        message = info_mock.call_args[0][1]
        self.assertIn('"status": "degraded"', message)
        self.assertIn('scheduler_start_failed', message)
        self.assertIn('auto_backup_check_failed', message)

    def test_startup_synchronizes_configured_telegram_webhook(self):
        with patch("app.startup.ensure_db_ready"), \
             patch("app.startup.sync_telegram_webhook_on_startup", return_value="synced") as sync_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads", app_env="test")

        sync_mock.assert_called_once_with()

    def test_run_startup_steps_passes_app_logger_to_auto_backup_check(self):
        with patch("app.startup.ensure_db_ready"),              patch("app.startup.start_scheduler"),              patch("app.startup.check_auto_backup") as backup_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads", app_env="development")
        backup_mock.assert_called_once_with("test.db", "uploads", logger=app.flask_app.logger)

    def test_startup_reports_telegram_webhook_configuration_problem(self):
        with patch("app.startup.ensure_db_ready"), \
             patch("app.startup.sync_telegram_webhook_on_startup", return_value="missing_base_url"), \
             patch("app.startup.logging.info") as info_mock:
            run_startup_steps(app.flask_app, "test.db", "uploads", app_env="test")

        message = info_mock.call_args[0][1]
        self.assertIn('"status": "degraded"', message)
        self.assertIn('telegram_webhook_missing_base_url', message)


class TestCheckAutoBackupAuditEvents(unittest.TestCase):
    def test_emits_startup_backup_created_for_db_and_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            with patch("app.services.backup_service.backup_db", return_value=("app_20990101_000000.db", 1)),                  patch("app.services.backup_service.backup_uploads", return_value=("uploads_20990101_000000.zip", 0)),                  patch("app.web.routes.helpers.admin_audit_helpers.log_admin_backup_event") as log_mock:
                check_auto_backup(db_path, "uploads_dir", logger="fake-logger")

            self.assertEqual(log_mock.call_count, 2)
            db_call, uploads_call = log_mock.call_args_list
            self.assertEqual(db_call.args[0], "fake-logger")
            self.assertEqual(db_call.kwargs["event"], "startup_backup_created")
            self.assertIsNone(db_call.kwargs["actor_id"])
            self.assertEqual(db_call.kwargs["backup_type"], "db")
            self.assertEqual(db_call.kwargs["pruned_count"], 1)
            self.assertEqual(uploads_call.kwargs["event"], "startup_backup_created")
            self.assertEqual(uploads_call.kwargs["backup_type"], "images")
            self.assertTrue(os.path.exists(os.path.join(tmp, ".last_backup")))

    def test_emits_startup_backup_failed_when_db_backup_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            with patch("app.services.backup_service.backup_db", side_effect=OSError("disk full")),                  patch("app.web.routes.helpers.admin_audit_helpers.log_admin_backup_event") as log_mock,                  patch("app.startup.logging.warning"):
                check_auto_backup(db_path, "uploads_dir", logger="fake-logger")

            log_mock.assert_called_once()
            self.assertEqual(log_mock.call_args.kwargs["event"], "startup_backup_failed")
            self.assertEqual(log_mock.call_args.kwargs["backup_type"], "db")
            self.assertEqual(log_mock.call_args.kwargs["error"], "disk full")
            self.assertFalse(os.path.exists(os.path.join(tmp, ".last_backup")))

    def test_emits_startup_backup_failed_with_images_type_when_uploads_backup_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            with patch("app.services.backup_service.backup_db", return_value=("app_20990101_000000.db", 0)),                  patch("app.services.backup_service.backup_uploads", side_effect=OSError("zip failed")),                  patch("app.web.routes.helpers.admin_audit_helpers.log_admin_backup_event") as log_mock,                  patch("app.startup.logging.warning"):
                check_auto_backup(db_path, "uploads_dir", logger="fake-logger")

            failure_call = log_mock.call_args_list[-1]
            self.assertEqual(failure_call.kwargs["event"], "startup_backup_failed")
            self.assertEqual(failure_call.kwargs["backup_type"], "images")
            self.assertFalse(os.path.exists(os.path.join(tmp, ".last_backup")))

    def test_uses_module_logger_when_none_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            with patch("app.services.backup_service.backup_db", return_value=("app_20990101_000000.db", 0)),                  patch("app.services.backup_service.backup_uploads", return_value=("uploads_20990101_000000.zip", 0)),                  patch("app.web.routes.helpers.admin_audit_helpers.log_admin_backup_event") as log_mock:
                check_auto_backup(db_path, "uploads_dir")

            called_logger = log_mock.call_args_list[0].args[0]
            self.assertEqual(called_logger.name, "app.startup")


if __name__ == "__main__":
    unittest.main()
