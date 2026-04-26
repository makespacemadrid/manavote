import pathlib
import sqlite3
import sys
import unittest
from unittest.mock import MagicMock, patch
import tempfile
import os
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.backup_service import backup_db


class TestBackupService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self._create_db()

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
        os.rmdir(self.temp_dir)

    def _create_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, title TEXT, amount REAL)")
        c.execute("INSERT INTO proposals (title, amount) VALUES ('Test', 100)")
        conn.commit()
        conn.close()

    def test_backup_creates_file(self):
        name, pruned = backup_db(self.db_path, keep_days=7)

        self.assertTrue(name.startswith("test_"))
        self.assertTrue(name.endswith(".db"))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, name)))
        self.assertEqual(pruned, 0)

    def test_backup_prunes_old_files(self):
        base_name = os.path.basename(self.db_path).replace(".db", "")
        old_time = datetime.now() - timedelta(days=10)
        old_name = os.path.join(self.temp_dir, f"{base_name}_{old_time.strftime('%Y%m%d_%H%M%S')}.db")

        conn = sqlite3.connect(old_name)
        c = conn.cursor()
        c.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, title TEXT, amount REAL)")
        conn.commit()
        conn.close()

        old_mtime = (datetime.now() - timedelta(days=10)).timestamp()
        os.utime(old_name, (old_mtime, old_mtime))

        name, pruned = backup_db(self.db_path, keep_days=7)

        self.assertEqual(pruned, 1)
        self.assertFalse(os.path.exists(old_name))


if __name__ == "__main__":
    unittest.main(verbosity=2)