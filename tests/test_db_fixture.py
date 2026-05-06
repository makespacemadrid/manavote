from app.db.connection import get_db


def test_isolated_db_path_fixture_provides_writable_database(isolated_db_path):
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS fixture_probe (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO fixture_probe (value) VALUES ('ok')")
    conn.commit()

    row = conn.execute("SELECT COUNT(*) as c FROM fixture_probe").fetchone()
    assert row[0] == 1
