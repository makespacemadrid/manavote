"""Regression checks for the user settings card layout."""

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_settings_actions_share_a_bottom_aligned_button_row():
    template = (ROOT / "templates" / "settings.html").read_text()

    assert ".user-settings-item > .email-settings-form" in template
    assert ".language-buttons {\n    display: grid;" in template
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in template
    assert ".language-buttons .btn {\n    min-width: 0;" in template
    assert 'class="email-settings-form"' in template
