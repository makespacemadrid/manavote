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
