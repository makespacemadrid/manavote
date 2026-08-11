"""Coverage checks for user-facing template and group-purchase translations."""

import ast
import re
from pathlib import Path

from translations import TRANSLATIONS


ROOT = Path(__file__).parents[1]


def test_literal_template_translation_keys_exist_in_every_locale():
    keys = set()
    pattern = re.compile(r'''["']([^"']+)["']\s*\|\s*(?:lang|t)\b''')
    for template in (ROOT / "templates").glob("*.html"):
        keys.update(pattern.findall(template.read_text()))

    for locale, translations in TRANSLATIONS.items():
        missing = keys - translations.keys()
        assert not missing, f"{locale} is missing template translations: {sorted(missing)}"


def test_literal_flash_messages_exist_in_every_locale():
    messages = set()
    for module in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(module.read_text())
        messages.update(
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "flash"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        )

    for locale, translations in TRANSLATIONS.items():
        missing = messages - translations.keys()
        assert not missing, f"{locale} is missing flash translations: {sorted(missing)}"


def test_flash_messages_are_rendered_through_translation_filter():
    base_template = (ROOT / "templates" / "base.html").read_text()

    assert "{{ message|lang }}" in base_template
