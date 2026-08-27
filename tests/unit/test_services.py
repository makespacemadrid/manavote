import sqlite3

from app.repositories.settings_repo import SettingsRepository
from app.services import voting_mode_service
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


def _settings(values):
    return lambda key, default=None: values.get(key, default)


def test_voting_mode_service_poll_vote_mode_defaults_and_invalid_falls_back():
    assert voting_mode_service.get_poll_vote_mode(_settings({})) == "both"
    assert voting_mode_service.get_poll_vote_mode(_settings({"poll_vote_mode": "bogus"})) == "both"
    assert voting_mode_service.get_poll_vote_mode(_settings({"poll_vote_mode": "WEB_ONLY"})) == "web_only"


def test_voting_mode_service_poll_channel_flags():
    web_only = _settings({"poll_vote_mode": "web_only"})
    telegram_only = _settings({"poll_vote_mode": "telegram_only"})
    assert voting_mode_service.is_web_poll_voting_enabled(web_only) is True
    assert voting_mode_service.is_telegram_poll_voting_enabled(web_only) is False
    assert voting_mode_service.is_web_poll_voting_enabled(telegram_only) is False
    assert voting_mode_service.is_telegram_poll_voting_enabled(telegram_only) is True


def test_voting_mode_service_require_linked_telegram_for_votes():
    assert voting_mode_service.require_linked_telegram_for_votes(_settings({})) is False
    assert voting_mode_service.require_linked_telegram_for_votes(
        _settings({"telegram_require_linked_vote": "true"})
    ) is True


def test_voting_mode_service_proposal_vote_mode_normalizes_invalid():
    assert voting_mode_service.get_proposal_vote_mode(_settings({"proposal_vote_mode": "nonsense"})) == "both"
    assert voting_mode_service.get_proposal_vote_mode(_settings({"proposal_vote_mode": "telegram_only"})) == "telegram_only"


def test_voting_mode_service_can_record_proposal_vote_by_source():
    web_only = _settings({"proposal_vote_mode": "web_only"})
    assert voting_mode_service.can_record_proposal_vote(web_only, "web") is True
    assert voting_mode_service.can_record_proposal_vote(web_only, "telegram") is False
    assert voting_mode_service.can_record_proposal_vote(web_only, "carrier_pigeon") is False


def test_voting_mode_service_is_registration_enabled():
    assert voting_mode_service.is_registration_enabled(_settings({})) is True
    assert voting_mode_service.is_registration_enabled(_settings({"registration_enabled": "false"})) is False
