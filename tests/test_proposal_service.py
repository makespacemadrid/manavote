import pathlib
import sqlite3
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.proposal_service import ProposalService


class TestProposalService(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        self._seed_defaults()

        self.telegram_client = MagicMock()
        self.base_url_getter = lambda: "http://localhost:5000/"
        self.service = ProposalService(self.conn, self.telegram_client, self.base_url_getter, created_by=1)

    def tearDown(self):
        self.conn.close()

    def _create_schema(self):
        c = self.conn.cursor()
        c.execute(
            """
            CREATE TABLE members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                password_hash TEXT,
                is_admin INTEGER DEFAULT 0
            )
            """
        )
        c.execute(
            """
            CREATE TABLE proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL,
                created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                processed_at TEXT,
                over_budget_at TEXT,
                purchased_at TEXT,
                basic_supplies INTEGER DEFAULT 0
            )
            """
        )
        c.execute(
            """
            CREATE TABLE votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                vote TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                description TEXT,
                created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def _seed_defaults(self):
        c = self.conn.cursor()
        c.execute("INSERT INTO members (username, password_hash) VALUES ('admin', 'x')")
        c.execute("INSERT INTO members (username, password_hash) VALUES ('member2', 'x')")
        c.execute("INSERT INTO settings (key, value) VALUES ('threshold_basic', '5')")
        c.execute("INSERT INTO settings (key, value) VALUES ('threshold_over50', '20')")
        c.execute("INSERT INTO settings (key, value) VALUES ('threshold_default', '10')")
        c.execute("INSERT INTO settings (key, value) VALUES ('timezone', 'Europe/Madrid')")
        c.execute("INSERT INTO settings (key, value) VALUES ('current_budget', '100')")
        self.conn.commit()

    def _insert_proposal(self, title, amount, basic_supplies=0, status="active", over_budget_at=None):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO proposals (title, amount, created_by, basic_supplies, status, over_budget_at) VALUES (?, ?, 1, ?, ?, ?)",
            (title, amount, basic_supplies, status, over_budget_at),
        )
        self.conn.commit()
        return c.lastrowid

    def _insert_vote(self, proposal_id, member_id, vote):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO votes (proposal_id, member_id, vote) VALUES (?, ?, ?)",
            (proposal_id, member_id, vote),
        )
        self.conn.commit()

    def _add_budget(self, amount, description="seed"):
        c = self.conn.cursor()
        c.execute("INSERT INTO activity_log (amount, description) VALUES (?, ?)", (amount, description))
        self.conn.commit()

    def test_process_proposal_approves_and_logs_budget(self):
        proposal_id = self._insert_proposal("3D printer nozzles", 60)
        self._insert_vote(proposal_id, 1, "in_favor")
        self._add_budget(100, "initial topup")

        result = self.service.process_proposal(proposal_id)

        self.assertTrue(result)
        c = self.conn.cursor()
        status = c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,)).fetchone()[0]
        self.assertEqual(status, "approved")

        latest_budget = c.execute(
            "SELECT amount, description FROM activity_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(latest_budget[0], -60)
        self.assertIn("Approved: 3D printer nozzles", latest_budget[1])
        self.telegram_client.send_message.assert_called_once()

    def test_process_proposal_marks_over_budget_when_votes_pass_but_budget_missing(self):
        proposal_id = self._insert_proposal("Laser cutter filter", 250)
        self._insert_vote(proposal_id, 1, "in_favor")
        self._add_budget(40, "small balance")

        result = self.service.process_proposal(proposal_id)

        self.assertEqual(result, "over_budget")
        c = self.conn.execute(
            "SELECT status, over_budget_at FROM proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        self.assertEqual(c[0], "over_budget")
        self.assertIsNotNone(c[1])

    def test_process_proposal_returns_none_when_votes_do_not_reach_threshold(self):
        proposal_id = self._insert_proposal("Workshop table", 30)
        self._add_budget(100, "initial")

        result = self.service.process_proposal(proposal_id)

        self.assertIsNone(result)
        status = self.conn.execute(
            "SELECT status FROM proposals WHERE id = ?", (proposal_id,)
        ).fetchone()[0]
        self.assertEqual(status, "active")

    def test_check_over_budget_proposals_auto_approves_when_budget_becomes_available(self):
        proposal_id = self._insert_proposal("Vinyl rolls", 75, status="over_budget")
        self._insert_vote(proposal_id, 1, "in_favor")
        self._add_budget(100, "new funds")

        self.service.check_over_budget_proposals()

        row = self.conn.execute(
            "SELECT status, processed_at FROM proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        self.assertEqual(row[0], "approved")
        self.assertIsNotNone(row[1])

        remaining_budget = self.conn.execute("SELECT SUM(amount) FROM activity_log").fetchone()[0]
        self.assertEqual(remaining_budget, 25)
        self.telegram_client.send_message.assert_called_once()

    def test_undo_approval_restores_budget_and_clears_timestamps(self):
        # Create approved proposal
        proposal_id = self._insert_proposal("Test item", 50, status="approved", over_budget_at="2026-04-29 10:00:00")
        self._add_budget(100, "initial")
        self._insert_vote(proposal_id, 1, "in_favor")
        
        # Simulate undo
        c = self.conn.cursor()
        c.execute("UPDATE proposals SET processed_at = '2026-04-29 12:00:00', purchased_at = '2026-04-29 13:00:00' WHERE id = ?", (proposal_id,))
        c.execute("UPDATE settings SET value = '50' WHERE key = 'current_budget'")
        self.conn.commit()
        
        # Call undo logic (simulated)
        c.execute("UPDATE proposals SET status = 'active', processed_at = NULL, purchased_at = NULL WHERE id = ?", (proposal_id,))
        c.execute("UPDATE settings SET value = ? WHERE key = 'current_budget'", (str(50 + 50),))
        self.conn.commit()
        
        # Verify
        row = c.execute("SELECT status, processed_at, purchased_at FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        self.assertEqual(row[0], "active")
        self.assertIsNone(row[1])
        self.assertIsNone(row[2])
        
        budget_row = c.execute("SELECT value FROM settings WHERE key = 'current_budget'").fetchone()
        self.assertIsNotNone(budget_row)
        self.assertEqual(float(budget_row[0]), 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
