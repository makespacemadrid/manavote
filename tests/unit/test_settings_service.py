from app.services.settings_service import get_enum_setting, normalize_public_base_url


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


def test_normalize_public_base_url_accepts_https_and_trims_trailing_slashes():
    assert normalize_public_base_url(" https://vote.example/community/// ") == "https://vote.example/community"


def test_normalize_public_base_url_allows_explicit_clear():
    assert normalize_public_base_url("  ") is None


def test_normalize_public_base_url_rejects_unsafe_or_ambiguous_values():
    for value in (
        "http://vote.example",
        "javascript:alert(1)",
        "https://user:secret@vote.example",
        "https://vote.example?redirect=other",
        "https://vote.example/#section",
        "not-a-url",
    ):
        try:
            normalize_public_base_url(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid Base URL: {value}")
