import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services import backup_service


class DummyApp:
    pass


class TestBackupScheduler(unittest.TestCase):
    @patch("app.services.backup_service.logging.getLogger")
    @patch("builtins.__import__", side_effect=ImportError("No module named apscheduler"))
    def test_start_scheduler_logs_install_hint_when_apscheduler_missing(self, _mock_import, mock_get_logger):
        app = DummyApp()

        scheduler = backup_service.start_scheduler(app, "/tmp/app.db")

        self.assertIsNone(scheduler)
        mock_get_logger.return_value.warning.assert_called()
        message = mock_get_logger.return_value.warning.call_args.args[0]
        self.assertIn("Install with `pip install APScheduler`", message)


if __name__ == "__main__":
    unittest.main()

import tempfile
import os
from datetime import datetime, timedelta


class TestUploadBackups(unittest.TestCase):
    def test_backup_uploads_creates_zip_and_prunes_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            uploads = os.path.join(tmp, "uploads")
            os.makedirs(uploads, exist_ok=True)
            with open(os.path.join(uploads, "a.txt"), "w") as f:
                f.write("x")

            backup_dir = os.path.join(tmp, "uploads_backups")
            os.makedirs(backup_dir, exist_ok=True)
            old_zip = os.path.join(backup_dir, "uploads_20000101_000000.zip")
            with open(old_zip, "w") as f:
                f.write("old")
            old_mtime = (datetime.now() - timedelta(days=10)).timestamp()
            os.utime(old_zip, (old_mtime, old_mtime))

            backup_name, pruned = backup_service.backup_uploads(uploads, keep_days=7, backup_root=backup_dir)

            self.assertTrue(backup_name.endswith('.zip'))
            self.assertTrue(os.path.exists(os.path.join(backup_dir, backup_name)))
            self.assertEqual(pruned, 1)


class TestDatabaseBackups(unittest.TestCase):
    def test_backup_db_creates_file_in_backup_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            with open(db_path, "w", encoding="utf-8") as f:
                f.write("sqlite-data")

            backup_dir = os.path.join(tmp, "backups")
            backup_name, pruned = backup_service.backup_db(db_path, keep_days=7, backup_root=backup_dir)

            self.assertEqual(pruned, 0)
            self.assertTrue(backup_name.startswith("app_"))
            self.assertTrue(os.path.exists(os.path.join(backup_dir, backup_name)))


class TestScheduledBackupJob(unittest.TestCase):
    """Scheduled (APScheduler) backups must emit the same structured audit
    events as admin-triggered ones, since APScheduler's own executor would
    otherwise swallow failures without a machine-readable signal."""

    def test_emits_scheduled_backup_created_on_success(self):
        app = DummyApp()
        app.logger = "fake-logger"
        backup_fn = lambda *a, **kw: ("app_20990101_000000.db", 3)

        with patch("app.web.routes.helpers.admin_audit_helpers.log_admin_backup_event") as log_mock:
            backup_service._scheduled_backup_job(app, "db", backup_fn, "/tmp/app.db")

        log_mock.assert_called_once()
        self.assertEqual(log_mock.call_args.args[0], "fake-logger")
        self.assertEqual(log_mock.call_args.kwargs["event"], "scheduled_backup_created")
        self.assertIsNone(log_mock.call_args.kwargs["actor_id"])
        self.assertEqual(log_mock.call_args.kwargs["backup_type"], "db")
        self.assertEqual(log_mock.call_args.kwargs["file_name"], "app_20990101_000000.db")
        self.assertEqual(log_mock.call_args.kwargs["status"], "ok")
        self.assertEqual(log_mock.call_args.kwargs["pruned_count"], 3)

    def test_emits_scheduled_backup_failed_when_backup_fn_raises(self):
        app = DummyApp()
        app.logger = "fake-logger"

        def _raise(*a, **kw):
            raise RuntimeError("disk full")

        with patch("app.web.routes.helpers.admin_audit_helpers.log_admin_backup_event") as log_mock:
            backup_service._scheduled_backup_job(app, "images", _raise, "/tmp/uploads")

        log_mock.assert_called_once()
        self.assertEqual(log_mock.call_args.kwargs["event"], "scheduled_backup_failed")
        self.assertEqual(log_mock.call_args.kwargs["backup_type"], "images")
        self.assertEqual(log_mock.call_args.kwargs["status"], "failed")
        self.assertEqual(log_mock.call_args.kwargs["reason_code"], "backup_exception")
        self.assertEqual(log_mock.call_args.kwargs["error"], "disk full")

    def test_start_scheduler_registers_jobs_that_call_backup_functions(self):
        app = DummyApp()
        app.logger = "fake-logger"

        with patch("app.services.backup_service.backup_db", return_value=("app_20990101_000000.db", 0)),              patch("app.services.backup_service.backup_uploads", return_value=("uploads_20990101_000000.zip", 0)):
            scheduler = backup_service.start_scheduler(app, "/tmp/app.db", "/tmp/uploads")
            try:
                jobs = {job.id: job for job in scheduler.get_jobs()}
                self.assertEqual(set(jobs), {"daily_backup", "daily_uploads_backup"})

                with patch("app.web.routes.helpers.admin_audit_helpers.log_admin_backup_event") as log_mock:
                    db_job = jobs["daily_backup"]
                    db_job.func(*db_job.args)
                    uploads_job = jobs["daily_uploads_backup"]
                    uploads_job.func(*uploads_job.args)

                self.assertEqual(log_mock.call_count, 2)
                events = {call.kwargs["backup_type"]: call.kwargs["event"] for call in log_mock.call_args_list}
                self.assertEqual(events, {"db": "scheduled_backup_created", "images": "scheduled_backup_created"})
            finally:
                scheduler.shutdown(wait=False)
