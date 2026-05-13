import importlib.util
import json
import os
import socket
import threading
import time
import urllib.request
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


def test_authorized_via_x_api_key_header():
    response = mcp_server.handle_request(
        {"jsonrpc": "2.0", "id": 11, "method": "initialize", "params": {}},
        headers={"x-api-key": "test-mcp-key"},
    )
    assert response["result"]["serverInfo"]["name"] == "manavote-mcp"


def test_authorized_via_bearer_header():
    response = mcp_server.handle_request(
        {"jsonrpc": "2.0", "id": 12, "method": "initialize", "params": {}},
        headers={"authorization": "Bearer test-mcp-key"},
    )
    assert response["result"]["serverInfo"]["name"] == "manavote-mcp"


def test_tools_call_list_proposals_invalid_status():
    response = mcp_server.handle_request(_req("tools/call", req_id=2, params={"name": "list_proposals", "arguments": {"status": "bogus"}}))
    assert response["error"]["code"] == -32602


def test_tools_list_includes_mcp_create_tools():
    response = mcp_server.handle_request(_req("tools/list", req_id=201))
    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert {"create_member", "create_proposal", "create_poll", "get_voting_settings", "update_voting_settings"}.issubset(tool_names)


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


def test_tools_call_get_voting_settings(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "_db_rows",
        lambda *_args, **_kwargs: [
            {"key": "poll_vote_mode", "value": "telegram_only"},
            {"key": "proposal_vote_mode", "value": "both"},
            {"key": "telegram_require_linked_vote", "value": "true"},
        ],
    )
    response = mcp_server.handle_request(_req("tools/call", req_id=41, params={"name": "get_voting_settings", "arguments": {}}))
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["poll_vote_mode"] == "telegram_only"
    assert payload["proposal_vote_mode"] == "both"
    assert payload["telegram_require_linked_vote"] is True


def test_tools_call_get_voting_settings_defaults(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [])
    response = mcp_server.handle_request(_req("tools/call", req_id=411, params={"name": "get_voting_settings", "arguments": {}}))
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload == {
        "poll_vote_mode": "both",
        "proposal_vote_mode": "both",
        "telegram_require_linked_vote": False,
    }


def test_tools_call_update_voting_settings_rejects_invalid_bool():
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=42,
            params={"name": "update_voting_settings", "arguments": {"telegram_require_linked_vote": "maybe"}},
        )
    )
    assert response["error"]["code"] == -32602


def test_tools_call_create_member(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(mcp_server, "_db_execute", lambda *_args, **_kwargs: 42)
    response = mcp_server.handle_request(
        _req("tools/call", req_id=5, params={"name": "create_member", "arguments": {"username": "bob", "password": "secret"}})
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["member_id"] == 42


def test_tools_call_create_member_rejects_duplicate_username(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 99}])
    response = mcp_server.handle_request(
        _req("tools/call", req_id=51, params={"name": "create_member", "arguments": {"username": "bob", "password": "secret"}})
    )
    assert response["error"]["code"] == -32010


def test_tools_call_create_proposal(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    monkeypatch.setattr(mcp_server, "_create_proposal_record", lambda *_args, **_kwargs: 77)
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=6,
            params={
                "name": "create_proposal",
                "arguments": {"title": "New printer", "amount": 150, "created_by": 1},
            },
        )
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["proposal_id"] == 77


def test_tools_call_create_proposal_rejects_missing_creator(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [])
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=61,
            params={"name": "create_proposal", "arguments": {"title": "New printer", "amount": 150, "created_by": 1}},
        )
    )
    assert response["error"]["code"] == -32004


def test_tools_call_create_proposal_rejects_non_positive_amount(monkeypatch):
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=62,
            params={"name": "create_proposal", "arguments": {"title": "New printer", "amount": 0, "created_by": 1}},
        )
    )
    assert response["error"]["code"] == -32602


def test_tools_call_create_poll(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    monkeypatch.setattr(mcp_server, "_db_execute", lambda *_args, **_kwargs: 13)
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=7,
            params={
                "name": "create_poll",
                "arguments": {"question": "Where meet?", "options": ["A", "B"], "created_by": 1},
            },
        )
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["poll_id"] == 13


def test_tools_call_create_poll_rejects_short_question(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=8,
            params={"name": "create_poll", "arguments": {"question": "Hey", "options": ["A", "B"], "created_by": 1}},
        )
    )
    assert response["error"]["code"] == -32602


def test_tools_call_create_poll_rejects_too_long_option(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=9,
            params={
                "name": "create_poll",
                "arguments": {"question": "Where should we meet?", "options": ["A" * 121, "B"], "created_by": 1},
            },
        )
    )
    assert response["error"]["code"] == -32602


def test_tools_call_create_poll_rejects_too_many_options(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=91,
            params={
                "name": "create_poll",
                "arguments": {
                    "question": "Where should we meet?",
                    "options": [str(i) for i in range(13)],
                    "created_by": 1,
                },
            },
        )
    )
    assert response["error"]["code"] == -32602


def test_tools_call_create_poll_rejects_missing_creator(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [])
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=10,
            params={
                "name": "create_poll",
                "arguments": {"question": "Where should we meet?", "options": ["A", "B"], "created_by": 99},
            },
        )
    )
    assert response["error"]["code"] == -32004


def test_mcp_create_tools_error_code_contract(monkeypatch):
    # validation class: invalid params
    invalid_member = mcp_server.handle_request(
        _req("tools/call", req_id=71, params={"name": "create_member", "arguments": {"username": "", "password": ""}})
    )
    assert invalid_member["error"]["code"] == -32602

    # conflict class: duplicate member username
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    duplicate_member = mcp_server.handle_request(
        _req("tools/call", req_id=72, params={"name": "create_member", "arguments": {"username": "alice", "password": "x"}})
    )
    assert duplicate_member["error"]["code"] == -32010

    # not-found class: missing creator member for create_proposal
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [])
    missing_creator = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=73,
            params={"name": "create_proposal", "arguments": {"title": "X", "amount": 12, "created_by": 999}},
        )
    )
    assert missing_creator["error"]["code"] == -32004


def test_http_mcp_endpoint_works():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    thread = threading.Thread(target=mcp_server.start_http_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True)
    thread.start()

    payload = json.dumps(_req("initialize", req_id=10)).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error = None
    for _ in range(10):
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:  # pragma: no cover - retry path
            last_error = exc
            time.sleep(0.02)
    else:
        raise last_error  # type: ignore[misc]

    assert body["id"] == 10
    assert body["result"]["serverInfo"]["name"] == "manavote-mcp"


def test_http_mcp_batch_works():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    thread = threading.Thread(target=mcp_server.start_http_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True)
    thread.start()

    batch = [
        _req("initialize", req_id=20),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(batch).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error = None
    for _ in range(10):
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:  # pragma: no cover - retry path
            last_error = exc
            time.sleep(0.02)
    else:
        raise last_error  # type: ignore[misc]

    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == 20


def test_http_mcp_endpoint_accepts_x_api_key_header():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    thread = threading.Thread(target=mcp_server.start_http_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True)
    thread.start()

    payload = json.dumps({"jsonrpc": "2.0", "id": 30, "method": "initialize", "params": {}}).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=payload,
        headers={"Content-Type": "application/json", "X-Api-Key": "test-mcp-key"},
        method="POST",
    )
    last_error = None
    for _ in range(10):
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:  # pragma: no cover - retry path
            last_error = exc
            time.sleep(0.02)
    else:
        raise last_error  # type: ignore[misc]

    assert body["id"] == 30
    assert body["result"]["serverInfo"]["name"] == "manavote-mcp"
