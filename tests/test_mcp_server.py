import importlib.util
import json
import os
from pathlib import Path

os.environ["MCP_API_KEY"] = "test-mcp-key"

spec = importlib.util.spec_from_file_location("manavote_mcp_server", Path("app/mcp_server.py"))
mcp_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mcp_server)


def _req(method, req_id=1, params=None):
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": {"api_key": "test-mcp-key", **(params or {})}}


def test_initialize_has_capabilities():
    response = mcp_server.handle_request(_req("initialize"))
    assert response["result"]["capabilities"] == {"tools": {}}


def test_unauthorized_request_rejected():
    response = mcp_server.handle_request({"jsonrpc": "2.0", "id": 9, "method": "initialize", "params": {"api_key": "bad"}})
    assert response["error"]["code"] == -32001


def test_tools_call_list_proposals_invalid_status():
    response = mcp_server.handle_request(_req("tools/call", req_id=2, params={"name": "list_proposals", "arguments": {"status": "bogus"}}))
    assert response["error"]["code"] == -32602


def test_tools_call_current_budget_returns_json_text(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"value": "300"}])

    response = mcp_server.handle_request(_req("tools/call", req_id=3, params={"name": "current_budget", "arguments": {}}))
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["current_budget"] == "300"


def test_notification_initialized_has_no_response():
    response = mcp_server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert response is None


def test_tools_call_list_member_telegram_links(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "_db_rows",
        lambda *_args, **_kwargs: [{"id": 1, "username": "alice", "telegram_username": "alice_tg", "telegram_user_id": 123, "linked": 1}],
    )

    response = mcp_server.handle_request(
        _req("tools/call", req_id=4, params={"name": "list_member_telegram_links", "arguments": {"include_unlinked": False, "limit": 10}})
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["count"] == 1
    assert payload["members"][0]["telegram_username"] == "alice_tg"
