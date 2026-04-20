import sqlite3


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def add_column_if_missing(cursor, table_name, ddl):
    column_name = ddl.split()[0]
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def run_migrations(cursor):
    add_column_if_missing(cursor, "settings", "url TEXT")
    add_column_if_missing(cursor, "proposals", "url TEXT")
    add_column_if_missing(cursor, "proposals", "image_filename TEXT")
    add_column_if_missing(cursor, "proposals", "purchased_at TEXT")
    try:
        cursor.execute("UPDATE proposals SET basic_supplies = 0 WHERE basic_supplies = 1 AND amount > 20")
    except sqlite3.OperationalError:
        pass
