from pathlib import Path
import re


TEMPLATES_WITH_CSRF_FORMS = [
    "templates/admin.html",
    "templates/dashboard.html",
    "templates/new_proposal.html",
    "templates/edit_proposal.html",
    "templates/proposal_detail.html",
    "templates/polls.html",
    "templates/settings.html",
    "templates/telegram_settings.html",
]


def test_admin_uses_shared_top_nav_partial():
    admin_template = Path("templates/admin.html").read_text(encoding="utf-8")
    assert '{% include "_top_nav.html" %}' in admin_template


def test_csrf_hidden_inputs_are_well_formed_in_key_templates():
    csrf_pattern = re.compile(
        r'<input\s+type="hidden"\s+name="csrf_token"\s+value="\{\{\s*csrf_token\(\)\s*\}\}"\s*/?>'
    )

    for template_path in TEMPLATES_WITH_CSRF_FORMS:
        template = Path(template_path).read_text(encoding="utf-8")
        if 'name="csrf_token"' not in template:
            continue

        for line in template.splitlines():
            if 'name="csrf_token"' in line:
                assert csrf_pattern.search(line.strip()), (
                    f"Malformed CSRF hidden input in {template_path}: {line.strip()}"
                )
