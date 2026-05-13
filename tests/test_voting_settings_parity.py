import importlib.util
import json
import os
from pathlib import Path

import app as budget_app


os.environ["MCP_API_KEY"] = "test-mcp-key"
spec = importlib.util.spec_from_file_location("manavote_mcp_server", Path("app/mcp_server.py"))
mcp_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mcp_server)
mcp_server.DB_PATH = budget_app.DB_PATH


def _mcp_req(name, arguments=None, req_id=1):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"api_key": "test-mcp-key", "name": name, "arguments": arguments or {}},
    }


def _with_admin_api_key():
    from app.web.routes import main_routes

    old = main_routes.ADMIN_API_KEY
    main_routes.ADMIN_API_KEY = "test-key"
    return old


def test_voting_settings_invalid_poll_mode_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"poll_vote_mode": "invalid_mode"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(_mcp_req("update_voting_settings", {"poll_vote_mode": "invalid_mode"}, req_id=2))

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_poll_vote_mode"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_invalid_linked_flag_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"telegram_require_linked_vote": "maybe"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("update_voting_settings", {"telegram_require_linked_vote": "maybe"}, req_id=3)
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_telegram_require_linked_vote"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_invalid_proposal_mode_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"proposal_vote_mode": "invalid_mode"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(_mcp_req("update_voting_settings", {"proposal_vote_mode": "invalid_mode"}, req_id=31))

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_proposal_vote_mode"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_missing_fields_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"unrelated": True},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(_mcp_req("update_voting_settings", {}, req_id=32))

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "no_changes_provided"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_success_shape_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={
                "poll_vote_mode": "both",
                "proposal_vote_mode": "telegram_only",
                "telegram_require_linked_vote": True,
            },
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req(
            "update_voting_settings",
            {
                "poll_vote_mode": "both",
                "proposal_vote_mode": "telegram_only",
                "telegram_require_linked_vote": True,
            },
            req_id=4,
        )
    )
    mcp_payload = json.loads(mcp["result"]["content"][0]["text"])
    rest_payload = rest.get_json()["settings"]
    for key in ("poll_vote_mode", "proposal_vote_mode", "telegram_require_linked_vote"):
        assert key in rest_payload
        assert key in mcp_payload


def test_member_telegram_link_listing_shape_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    conn = budget_app.get_db()
    conn.execute("DELETE FROM members")
    conn.executemany(
        "INSERT INTO members (id, username, password_hash, is_admin, telegram_username, telegram_user_id) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "linked", "x", 0, "linked_tg", 7001),
            (2, "missing_username", "x", 0, "", 7002),
            (3, "missing_user_id", "x", 0, "only_name", None),
            (4, "unlinked", "x", 0, None, None),
        ],
    )
    conn.commit()
    conn.close()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/telegram?include_unlinked=true&limit=50&offset=0",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("list_member_telegram_links", {"include_unlinked": True, "limit": 50, "offset": 0}, req_id=5)
    )

    assert rest.status_code == 200
    rest_members = rest.get_json()["members"]
    mcp_members = json.loads(mcp["result"]["content"][0]["text"])["members"]
    assert len(rest_members) == len(mcp_members) == 4

    rest_view = {row["username"]: (row["linked"], row["link_state"]) for row in rest_members}
    mcp_view = {row["username"]: (row["linked"], row["link_state"]) for row in mcp_members}
    assert rest_view == mcp_view


def test_member_telegram_link_listing_invalid_limit_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/telegram?limit=999",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("list_member_telegram_links", {"limit": 999}, req_id=6)
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "limit_out_of_range"
    assert mcp["error"]["code"] == -32602
