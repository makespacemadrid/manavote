import os
import pathlib
import tempfile


def pytest_sessionstart(session):
    temp_dir = tempfile.TemporaryDirectory()
    session._isolated_db_temp_dir = temp_dir
    db_path = pathlib.Path(temp_dir.name) / "test_session.db"
    os.environ["APP_DB_PATH"] = str(db_path)
