from unittest.mock import patch

from app.web.routes.main_routes import can_record_proposal_vote, get_proposal_vote_mode


def test_get_proposal_vote_mode_defaults_to_both_for_invalid_value():
    with patch("app.web.routes.main_routes.get_setting_value", return_value="invalid"):
        assert get_proposal_vote_mode() == "both"


def test_can_record_proposal_vote_matrix_web_only():
    with patch("app.web.routes.main_routes.get_setting_value", return_value="web_only"):
        assert can_record_proposal_vote("web") is True
        assert can_record_proposal_vote("telegram") is False


def test_can_record_proposal_vote_matrix_telegram_only():
    with patch("app.web.routes.main_routes.get_setting_value", return_value="telegram_only"):
        assert can_record_proposal_vote("web") is False
        assert can_record_proposal_vote("telegram") is True


def test_can_record_proposal_vote_matrix_both():
    with patch("app.web.routes.main_routes.get_setting_value", return_value="both"):
        assert can_record_proposal_vote("web") is True
        assert can_record_proposal_vote("telegram") is True


def test_can_record_proposal_vote_rejects_unknown_source():
    with patch("app.web.routes.main_routes.get_setting_value", return_value="both"):
        assert can_record_proposal_vote("email") is False


from app.services.proposal_vote_service import can_record_proposal_vote_source, normalize_proposal_vote_mode


def test_service_normalize_defaults_to_both():
    assert normalize_proposal_vote_mode(None) == "both"
    assert normalize_proposal_vote_mode("invalid") == "both"


def test_service_source_matrix():
    assert can_record_proposal_vote_source("web_only", "web") is True
    assert can_record_proposal_vote_source("web_only", "telegram") is False
    assert can_record_proposal_vote_source("telegram_only", "web") is False
    assert can_record_proposal_vote_source("telegram_only", "telegram") is True
    assert can_record_proposal_vote_source("both", "web") is True
    assert can_record_proposal_vote_source("both", "telegram") is True
