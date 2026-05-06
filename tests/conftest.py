import sys
import os
import pathlib
import shutil
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.db.connection import set_db_path


def pytest_sessionstart(session):
    temp_dir = tempfile.TemporaryDirectory()
    session._isolated_db_temp_dir = temp_dir
    db_path = pathlib.Path(temp_dir.name) / "test_session.db"
    os.environ["APP_DB_PATH"] = str(db_path)


@pytest.fixture
def isolated_db_path(tmp_path):
    """Per-test database path cloned from the session DB when available."""
    source = pathlib.Path(os.environ.get("APP_DB_PATH", ""))
    test_db_path = tmp_path / "isolated_test.db"

    if source.exists():
        shutil.copy2(source, test_db_path)
    else:
        test_db_path.touch()

    previous_env = os.environ.get("APP_DB_PATH")
    os.environ["APP_DB_PATH"] = str(test_db_path)
    set_db_path(str(test_db_path))

    try:
        yield test_db_path
    finally:
        if previous_env is None:
            os.environ.pop("APP_DB_PATH", None)
        else:
            os.environ["APP_DB_PATH"] = previous_env
        set_db_path(os.environ.get("APP_DB_PATH", str(source)))
