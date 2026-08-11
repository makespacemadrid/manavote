"""Integration checks for the progressively migrated React application shell."""

import html
import json
import re
from pathlib import Path

from flask import render_template, session

from app import app


ROOT = Path(__file__).parents[1]
PROPS_PATTERN = re.compile(r'data-react-props="([^"]+)"')


def _render_navigation(*, path="/dashboard", is_admin=False):
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
        assert "align-items: center" in styles
        assert ".btn + .btn" not in styles


def test_navigation_serializes_hydration_props_and_current_page_markup():
    markup = _render_navigation(path="/dashboard")
    props = _navigation_props(markup)

    assert props["currentPath"] == "/dashboard"
    assert props["username"]["value"] == "test-member"
    assert props["username"]["navigationLabel"] == "Primary navigation"
    assert any(link == {"href": "/dashboard", "label": "Dashboard"} for link in props["links"])
    assert '<nav class="nav"' in markup
    assert 'href="/dashboard" aria-current="page"' in markup
    assert 'aria-controls="primary-navigation"' in markup


def test_navigation_only_exposes_admin_link_to_admin_sessions():
    member_links = _navigation_props(_render_navigation(is_admin=False))["links"]
    admin_links = _navigation_props(_render_navigation(is_admin=True))["links"]

    assert "Admin" not in {link["label"] for link in member_links}
    assert "Admin" in {link["label"] for link in admin_links}
