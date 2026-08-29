from pathlib import Path
import re

from app.web.routes.main_routes import app, currency_filter


TEMPLATES_WITH_CSRF_FORMS = [
    "templates/admin.html",
    "templates/proposals.html",
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


def test_admin_warns_when_public_base_url_is_missing():
    admin_template = Path("templates/admin.html").read_text(encoding="utf-8")

    assert "{% set telegram_base_url = get_setting_value('url', '')|trim %}" in admin_template
    assert "{% if not telegram_base_url %}" in admin_template
    assert 'role="status" class="telegram-base-url-warning"' in admin_template
    assert "Public Base URL missing guidance" in admin_template
    assert 'value="{{ telegram_base_url }}"' in admin_template


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


def test_proposal_filters_use_shared_chips_and_expose_truncated_titles():
    template = Path("templates/proposals.html").read_text(encoding="utf-8")

    assert "{% set filter_chips = [" in template
    assert 'class="filter-chip{{' in template
    assert 'aria-current="page"' in template
    assert 'title="{{ p.title }}"' in template
    assert 'class="vote-approve"' in template


def test_poll_voting_leads_results_and_uses_shared_vote_styling():
    template = Path("templates/polls.html").read_text(encoding="utf-8")

    vote_card = template.index("{# Card 1: Vote via web #}")
    results_card = template.index("{# Card 2: Votes so far with bars #}")
    assert vote_card < results_card
    assert 'class="vote-btn approve poll-vote-submit"' in template
    assert 'class="poll-result-fill color-{{ (loop.index0 % 5) + 1 }}"' in template


def test_budget_chart_is_self_hosted_and_has_distinct_controls():
    template = Path("templates/budget.html").read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net" not in template
    assert "vendor/chart.js/chart.umd.js" in template
    assert 'class="chart-range-btn active" data-days="90"' in template
    assert "applyChartRange('90')" in template
    assert "Activity table filters" in template


def test_currency_filter_adds_thousands_separators():
    assert currency_filter(1234567.8) == "1,234,567.80"
    assert currency_filter(-2500) == "-2,500.00"


def test_shared_danger_modal_has_accessible_keyboard_behavior():
    modal = Path("templates/_danger_action_modal.html").read_text(encoding="utf-8")
    base = Path("templates/base.html").read_text(encoding="utf-8")

    assert 'role="dialog"' in modal
    assert 'aria-modal="true"' in modal
    assert "event.key === 'Escape'" in modal
    assert "event.key !== 'Tab'" in modal
    assert "_danger_action_modal.html" in base
    assert "user-scalable=no" not in base
    assert "maximum-scale" not in base


def test_member_templates_use_shared_confirmation_and_post_mutations():
    templates = {
        path.name: path.read_text(encoding="utf-8")
        for path in Path("templates").glob("*.html")
    }

    assert not any("return confirm(" in template for template in templates.values())
    detail = templates["proposal_detail.html"]
    proposals = templates["proposals.html"]
    assert 'method="POST" action="{{ url_for(\'proposals.withdraw_vote\'' in detail
    assert 'method="POST" action="{{ url_for(\'proposals.undo_approve\'' in detail
    assert 'method="POST" action="{{ url_for(\'proposals.undo_approve\'' in proposals


def test_undo_and_withdraw_routes_reject_get_requests():
    client = app.test_client()

    assert client.get("/undo/1").status_code == 405
    assert client.get("/withdraw-vote/1").status_code == 405
