import sqlite3

from app.repositories.settings_repo import SettingsRepository
from app.services.auth_service import verify_and_migrate_password
from app.services.budget_service import calculate_min_backers


def test_calculate_min_backers_variants():
    thresholds = {"basic": 5, "over50": 20, "default": 10}
    assert calculate_min_backers(50, 15, 1, thresholds) == 2
    assert calculate_min_backers(50, 75, 0, thresholds) == 10
    assert calculate_min_backers(3, 25, 0, thresholds) == 1


def test_verify_and_migrate_password_legacy_sha256():
    import hashlib

    pw = "secret"
    legacy = hashlib.sha256(pw.encode()).hexdigest()
    valid, migrated = verify_and_migrate_password(legacy, pw)
    assert valid is True
    assert migrated is not None


def test_settings_repository_threshold_defaults():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    repo = SettingsRepository(conn)
    assert repo.get_thresholds() == {"basic": 5, "over50": 20, "default": 10}
