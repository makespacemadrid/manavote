"""Integration checks for the progressively migrated React application shell."""

import html
import json
import re
from pathlib import Path

from flask import render_template, session

from app import app


ROOT = Path(__file__).parents[1]
PROPS_PATTERN = re.compile(r'data-react-props="([^"]+)"')


def _render_navigation(*, path="/proposals", is_admin=False):
    with app.test_request_context(path):
        session.update(username="test-member", member_id=42, is_admin=is_admin)
        return render_template("_top_nav.html")


def _navigation_props(markup):
    match = PROPS_PATTERN.search(markup)
    assert match, "navigation must expose serialized React properties"
    return json.loads(html.unescape(match.group(1)))


def test_base_loads_external_react_assets_without_inline_navigation_script():
    template = (ROOT / "templates" / "base.html").read_text()

    assert "react/style.css" in template
    assert "react/app.js" in template
    assert "classList.toggle('mobile-open')" not in template


def test_development_fallback_assets_are_served_by_flask():
    client = app.test_client()

    script = client.get("/static/react/app.js")
    stylesheet = client.get("/static/react/style.css")

    assert script.status_code == 200
    assert script.mimetype in {"application/javascript", "text/javascript"}
    assert stylesheet.status_code == 200
    assert stylesheet.mimetype == "text/css"


def test_button_groups_use_gap_without_misaligned_adjacent_margins():
    source_styles = (ROOT / "frontend" / "src" / "styles.css").read_text()
    fallback_styles = (ROOT / "static" / "react" / "style.css").read_text()

    for styles in (source_styles, fallback_styles):
        assert ".button-row" in styles
        assert ".button-row { display: flex; align-items: stretch" in styles
        assert ".button-row > form > .btn { height: 100%; }" in styles
        assert "font-family: inherit" in styles
        assert ".btn + .btn" not in styles


def test_group_purchase_actions_use_shared_aligned_button_row():
    template = (ROOT / "templates" / "group_purchases.html").read_text()

    assert '<div class="button-row" style="margin:10px 0;">' in template


def test_navigation_serializes_hydration_props_and_current_page_markup():
    markup = _render_navigation(path="/proposals")
    props = _navigation_props(markup)

    assert props["currentPath"] == "/proposals"
    assert props["username"]["value"] == "test-member"
    assert props["username"]["navigationLabel"] == "Primary navigation"
    assert any(link == {"href": "/proposals", "label": "Proposals"} for link in props["links"])
    assert props["links"][:4] == [
        {"href": "/proposals", "label": "Proposals"},
        {"href": "/polls", "label": "Polls"},
        {"href": "/group-purchases", "label": "Group purchases"},
        {"href": "/budget", "label": "Budget"},
    ]
    assert '<nav class="nav"' in markup
    assert 'href="/proposals" aria-current="page"' in markup
    assert 'aria-controls="primary-navigation"' in markup
    assert re.search(r'data-react-props="[^"]+"><nav', markup)
    assert "</nav></div>" in markup


def test_react_navigation_reports_successful_hydration_for_browser_diagnostics():
    component = (ROOT / "frontend" / "src" / "Nav.jsx").read_text()

    assert "data-react-hydrated" in component


def test_navigation_only_exposes_admin_link_to_admin_sessions():
    member_links = _navigation_props(_render_navigation(is_admin=False))["links"]
    admin_links = _navigation_props(_render_navigation(is_admin=True))["links"]

    assert "Admin" not in {link["label"] for link in member_links}
    assert "Admin" in {link["label"] for link in admin_links}
