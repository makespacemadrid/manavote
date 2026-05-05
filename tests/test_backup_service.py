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
