import sqlite3
import unittest
from unittest.mock import patch

import app
from app.startup import run_startup_steps


class TestAppStartup(unittest.TestCase):
    def test_create_app_fails_fast_on_db_initialization_error(self):
        with patch("app.run_startup_steps", side_effect=sqlite3.OperationalError("boom")):
            with self.assertRaises(RuntimeError):
                app.create_app()

    def test_run_startup_steps_executes_in_order(self):
        events = []
        with patch("app.startup.ensure_db_ready", side_effect=lambda: events.append("db")),              patch("app.startup.check_auto_backup", side_effect=lambda *_: events.append("backup")),              patch("app.startup.start_scheduler", side_effect=lambda *_: events.append("scheduler")):
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


if __name__ == "__main__":
    unittest.main()
