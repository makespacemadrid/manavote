import sys
import os
import pathlib
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

def pytest_sessionstart(session):
    temp_dir = tempfile.TemporaryDirectory()
    session._isolated_db_temp_dir = temp_dir
    db_path = pathlib.Path(temp_dir.name) / "test_session.db"
    os.environ["APP_DB_PATH"] = str(db_path)


@pytest.fixture
def isolated_db_path(tmp_path, monkeypatch):
    """Fresh writable database with isolated connection and runtime paths."""
    # Import after pytest_sessionstart sets APP_DB_PATH; importing the package
    # earlier boots the application against the checkout's development database.
    import app
    from app.db.connection import set_db_path
    from app.web.routes import main_routes

    source = pathlib.Path(os.environ.get("APP_DB_PATH", ""))
    test_db_path = tmp_path / "isolated_test.db"

    # Do not copy members/identities mutated by earlier session-level tests.
    # Existing application setup initializes this fresh file on first access.
    test_db_path.touch()

    previous_env = os.environ.get("APP_DB_PATH")
    os.environ["APP_DB_PATH"] = str(test_db_path)
    set_db_path(str(test_db_path))
    monkeypatch.setattr(main_routes, "DB_PATH", str(test_db_path))
    monkeypatch.setattr(app, "DB_PATH", str(test_db_path))

    try:
        yield test_db_path
    finally:
        if previous_env is None:
            os.environ.pop("APP_DB_PATH", None)
        else:
            os.environ["APP_DB_PATH"] = previous_env
        set_db_path(os.environ.get("APP_DB_PATH", str(source)))
