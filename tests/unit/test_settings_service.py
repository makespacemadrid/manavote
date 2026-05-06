from app.services.settings_service import get_enum_setting


def test_get_enum_setting_returns_normalized_value():
    def getter(_key, _default):
        return " WEB_ONLY "

    value = get_enum_setting(getter, "poll_vote_mode", "both", {"both", "web_only"})
    assert value == "web_only"


def test_get_enum_setting_falls_back_to_default_on_invalid():
    def getter(_key, _default):
        return "invalid"

    value = get_enum_setting(getter, "poll_vote_mode", "both", {"both", "web_only"})
    assert value == "both"
