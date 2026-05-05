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

            backup_name, pruned = backup_service.backup_uploads(uploads, keep_days=7)

            self.assertTrue(backup_name.endswith('.zip'))
            self.assertTrue(os.path.exists(os.path.join(backup_dir, backup_name)))
            self.assertEqual(pruned, 1)
