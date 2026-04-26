import sqlite3
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parents[2] / "app.db")


def set_db_path(path: str) -> None:
    global DB_PATH
    DB_PATH = path


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
