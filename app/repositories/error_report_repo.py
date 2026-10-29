"""Bounded diagnostic storage, separate from application data and backups."""
from pathlib import Path
from contextlib import closing
import sqlite3


class ErrorReportRepository:
    def __init__(self, path):
        self.path = str(path)

    def connect(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=1)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY, created_at TEXT, level TEXT, logger TEXT, details TEXT)')
        except Exception:
            conn.close()
            raise
        return conn

    def append(self, created_at, level, logger, details):
        with closing(self.connect()) as conn, conn:
            conn.execute('INSERT INTO errors(created_at,level,logger,details) VALUES (?,?,?,?)', (created_at, level, logger, details))
            conn.execute('DELETE FROM errors WHERE id NOT IN (SELECT id FROM errors ORDER BY id DESC LIMIT 200)')

    def recent(self):
        with closing(self.connect()) as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM errors ORDER BY id DESC LIMIT 200')]
