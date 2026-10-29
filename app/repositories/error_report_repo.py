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
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY, created_at TEXT, level TEXT, logger TEXT, details TEXT)')
            if 'processed_at' not in {row[1] for row in conn.execute('PRAGMA table_info(errors)')}:
                conn.execute('ALTER TABLE errors ADD COLUMN processed_at TEXT')
            conn.commit()
        except Exception:
            conn.close()
            raise
        return conn

    def append(self, created_at, level, logger, details):
        with closing(self.connect()) as conn, conn:
            conn.execute('INSERT INTO errors(created_at,level,logger,details) VALUES (?,?,?,?)', (created_at, level, logger, details))
            for archived in (False, True):
                predicate = 'IS NOT NULL' if archived else 'IS NULL'
                conn.execute(f'DELETE FROM errors WHERE processed_at {predicate} AND id NOT IN (SELECT id FROM errors WHERE processed_at {predicate} ORDER BY id DESC LIMIT 200)')

    def recent(self, archived=False):
        with closing(self.connect()) as conn:
            predicate = 'IS NOT NULL' if archived else 'IS NULL'
            return [dict(row) for row in conn.execute(f'SELECT * FROM errors WHERE processed_at {predicate} ORDER BY id DESC LIMIT 200')]

    def export_pending(self, render, processed_at):
        with closing(self.connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = [dict(row) for row in conn.execute('SELECT * FROM errors WHERE processed_at IS NULL ORDER BY id DESC LIMIT 200')]
            for row in rows:
                row['processed_at'] = processed_at
            result = render(rows)
            conn.executemany('UPDATE errors SET processed_at = ? WHERE id = ?', [(processed_at, row['id']) for row in rows])
            conn.execute('DELETE FROM errors WHERE processed_at IS NOT NULL AND id NOT IN (SELECT id FROM errors WHERE processed_at IS NOT NULL ORDER BY id DESC LIMIT 200)')
            return result
