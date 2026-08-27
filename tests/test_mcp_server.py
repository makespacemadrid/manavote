import importlib.util
import json
import os
import socket
import sqlite3
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


def test_non_object_params_are_rejected_without_server_error():
    response = mcp_server.handle_request(
        {"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": []},
        headers={"x-api-key": "test-mcp-key"},
    )
    assert response["error"] == {"code": -32602, "message": "Invalid params: params must be an object"}


def test_non_object_tool_arguments_are_rejected_even_when_empty():
    for arguments in ([], "", False, 0):
        response = mcp_server.handle_request(
            _req("tools/call", req_id=101, params={"name": "current_budget", "arguments": arguments})
        )
        assert response["error"] == {
            "code": -32602,
            "message": "Invalid params: arguments must be an object",
        }


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


def test_tools_call_list_proposals_rejects_invalid_pagination():
    for arguments in ({"limit": 0}, {"limit": 201}, {"offset": -1}, {"limit": "many"}):
        response = mcp_server.handle_request(
            _req("tools/call", req_id=19, params={"name": "list_proposals", "arguments": arguments})
        )
        assert response["error"]["code"] == -32602


def test_tools_list_advertises_domain_proposal_statuses():
    response = mcp_server.handle_request(_req("tools/list", req_id=20))
    list_proposals = next(tool for tool in response["result"]["tools"] if tool["name"] == "list_proposals")

    assert set(list_proposals["inputSchema"]["properties"]["status"]["enum"]) == {
        "active",
        "approved",
        "over_budget",
        "rejected",
    }


def test_tools_call_list_proposals_filters_old_active_proposals(monkeypatch):
    captured = {}

    def fake_db_rows(query, params=()):
        captured.update(query=query, params=params)
        return []

    monkeypatch.setattr(mcp_server, "_db_rows", fake_db_rows)
    response = mcp_server.handle_request(
        _req("tools/call", req_id=21, params={"name": "list_proposals", "arguments": {"age": "old"}})
    )

    assert "status = 'active'" in captured["query"]
    assert "datetime(p.created_at) <= datetime(?)" in captured["query"]
    assert len(captured["params"]) == 3
    assert json.loads(response["result"]["content"][0]["text"])["count"] == 0


def test_tools_call_list_proposals_rejects_incompatible_age_and_status():
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=22,
            params={"name": "list_proposals", "arguments": {"age": "recent", "status": "approved"}},
        )
    )
    assert response["error"]["code"] == -32602


def test_tools_list_includes_mcp_create_tools():
    response = mcp_server.handle_request(_req("tools/list", req_id=201))
    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert {
        "create_member",
        "create_proposal",
        "create_poll",
        "get_voting_settings",
        "update_voting_settings",
        "list_user_statistics",
    }.issubset(tool_names)


def test_tools_call_list_user_statistics(monkeypatch):
    row = {
        "id": 1,
        "username": "alice",
        "email": "alice@example.com",
        "is_admin": 0,
        "proposal_vote_count": 3,
        "proposal_count": 2,
        "approved_proposal_count": 1,
        "proposed_budget": 250,
        "approved_proposal_budget": 100,
        "approved_budget_percentage": 40,
        "comment_count": 4,
        "poll_vote_count": 5,
        "poll_count": 1,
        "open_poll_count": 1,
        "closed_poll_count": 0,
        "created_poll_vote_count": 6,
        "average_votes_per_created_poll": 6,
        "group_purchase_count": 2,
        "open_group_purchase_count": 1,
        "created_group_purchase_order_value": 125,
        "created_group_purchase_participant_count": 4,
    }
    monkeypatch.setattr(
        mcp_server,
        "_db_rows",
        lambda query, *_args, **_kwargs: [{"total": 1}] if "COUNT(*) AS total" in query else [row],
    )

    response = mcp_server.handle_request(
        _req("tools/call", req_id=202, params={"name": "list_user_statistics", "arguments": {"limit": 25}})
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    expected_row = {key: value for key, value in row.items() if key != "email"}
    assert payload == {"count": 1, "total": 1, "limit": 25, "offset": 0, "users": [expected_row]}


def test_tools_call_list_user_statistics_email_is_explicit_opt_in(monkeypatch):
    row = {"id": 1, "username": "alice", "email": "alice@example.com"}
    monkeypatch.setattr(
        mcp_server,
        "_db_rows",
        lambda query, *_args, **_kwargs: [{"total": 1}] if "COUNT(*) AS total" in query else [row],
    )
    response = mcp_server.handle_request(_req("tools/call", req_id=212, params={
        "name": "list_user_statistics", "arguments": {"include_email": True},
    }))
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["users"][0]["email"] == "alice@example.com"


def test_tools_call_list_user_statistics_rejects_invalid_pagination():
    for arguments in ({"offset": -1}, {"limit": 0}, {"limit": 501}, {"limit": "many"}):
        response = mcp_server.handle_request(
            _req("tools/call", req_id=203, params={"name": "list_user_statistics", "arguments": arguments})
        )
        assert response["error"]["code"] == -32602


def test_tools_call_list_user_statistics_filters_and_ranks_budget(monkeypatch):
    captured = []

    def fake_db_rows(query, params=()):
        captured.append((query, params))
        return []

    monkeypatch.setattr(mcp_server, "_db_rows", fake_db_rows)
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=204,
            params={
                "name": "list_user_statistics",
                "arguments": {
                    "username": "Alice",
                    "sort_by": "approved_budget_percentage",
                    "sort_direction": "asc",
                },
            },
        )
    )

    page_query, page_params = captured[0]
    assert "WHERE m.username = ? COLLATE NOCASE" in page_query
    assert "ORDER BY approved_budget_percentage ASC" in page_query
    assert page_params == ("Alice", 100, 0)
    assert json.loads(response["result"]["content"][0]["text"])["users"] == []


def test_tools_call_list_user_statistics_rejects_invalid_budget_query():
    for arguments in (
        {"username": "  "},
        {"sort_by": "money"},
        {"sort_direction": "sideways"},
    ):
        response = mcp_server.handle_request(
            _req("tools/call", req_id=205, params={"name": "list_user_statistics", "arguments": arguments})
        )
        assert response["error"]["code"] == -32602


def test_tools_call_list_user_statistics_ranks_created_poll_engagement(monkeypatch):
    captured = []
    monkeypatch.setattr(
        mcp_server,
        "_db_rows",
        lambda query, params=(): captured.append((query, params)) or [],
    )

    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=206,
            params={
                "name": "list_user_statistics",
                "arguments": {"sort_by": "average_votes_per_created_poll"},
            },
        )
    )

    assert "ORDER BY average_votes_per_created_poll DESC" in captured[0][0]
    assert json.loads(response["result"]["content"][0]["text"])["users"] == []


def test_tools_call_list_polls_returns_creator_options_and_votes(monkeypatch):
    captured = {}

    def fake_db_rows(query, params=()):
        if "FROM poll_votes WHERE" in query:
            return [
                {"poll_id": 4, "option_index": 0, "votes": 5},
                {"poll_id": 4, "option_index": 1, "votes": 2},
            ]
        captured.update(query=query, params=params)
        return [{
            "id": 4, "question": "Choose", "options_json": '["A", "B"]',
            "status": "closed", "created_at": "2026-01-01", "closes_at": None,
            "created_by": 2, "username": "alice", "total_votes": 7,
        }]

    monkeypatch.setattr(mcp_server, "_db_rows", fake_db_rows)
    response = mcp_server.handle_request(
        _req("tools/call", req_id=207, params={"name": "list_polls", "arguments": {
            "status": "closed", "username": "Alice",
        }})
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert "p.status = ?" in captured["query"]
    assert "m.username = ? COLLATE NOCASE" in captured["query"]
    assert captured["params"] == ("closed", "Alice", 20, 0)
    assert payload["polls"][0]["options"] == ["A", "B"]
    assert payload["polls"][0]["results"] == [
        {"option_index": 0, "option": "A", "votes": 5},
        {"option_index": 1, "option": "B", "votes": 2},
    ]
    assert payload["polls"][0]["total_votes"] == 7
    assert "options_json" not in payload["polls"][0]


def test_tools_call_list_polls_rejects_invalid_filters_and_pagination():
    for arguments in ({"status": "active"}, {"username": " "}, {"limit": 201}, {"offset": -1}):
        response = mcp_server.handle_request(
            _req("tools/call", req_id=208, params={"name": "list_polls", "arguments": arguments})
        )
        assert response["error"]["code"] == -32602


def test_tools_call_list_group_purchases_returns_costs_participants_and_payments(monkeypatch):
    captured = {}

    def fake_db_rows(query, params=()):
        if "FROM group_purchase_components" in query:
            return [{"id": 10, "name": "Keyboard", "unit_price": 20, "total_quantity": 3}]
        if "FROM group_purchase_shared_costs" in query:
            return [{"label": "Shipping", "amount": 10}]
        if "FROM group_purchase_quantities" in query:
            return [
                {"member_id": 2, "username": "alice", "selection_amount": 40, "paid": 1},
                {"member_id": 3, "username": "bob", "selection_amount": 20, "paid": 0},
            ]
        captured.update(query=query, params=params)
        return [{
            "id": 5, "title": "Keyboards", "description": "Bulk order", "status": "open",
            "created_at": "2026-01-01", "deadline": None, "url": None,
            "payment_method": "cash", "created_by": 2, "username": "alice",
        }]

    monkeypatch.setattr(mcp_server, "_db_rows", fake_db_rows)
    response = mcp_server.handle_request(
        _req("tools/call", req_id=209, params={"name": "list_group_purchases", "arguments": {
            "status": "open", "username": "Alice",
        }})
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    purchase = payload["group_purchases"][0]

    assert captured["params"] == ("open", "Alice", 20, 0)
    assert purchase["selection_total"] == 60
    assert purchase["shared_cost_total"] == 10
    assert purchase["total_cost"] == 70
    assert purchase["participant_count"] == 2
    assert purchase["paid_participant_count"] == 1
    assert [person["amount_owed"] for person in purchase["participants"]] == [46.67, 23.33]


def test_tools_call_list_group_purchases_rejects_invalid_filters_and_pagination():
    for arguments in ({"status": " "}, {"status": "cancelled"}, {"username": " "}, {"limit": 201}, {"offset": -1}):
        response = mcp_server.handle_request(
            _req("tools/call", req_id=210, params={"name": "list_group_purchases", "arguments": arguments})
        )
        assert response["error"]["code"] == -32602


def test_tools_call_list_user_statistics_ranks_group_purchase_value(monkeypatch):
    captured = []
    monkeypatch.setattr(
        mcp_server,
        "_db_rows",
        lambda query, params=(): captured.append((query, params)) or [],
    )
    mcp_server.handle_request(_req("tools/call", req_id=211, params={
        "name": "list_user_statistics",
        "arguments": {"sort_by": "created_group_purchase_order_value"},
    }))
    assert "ORDER BY created_group_purchase_order_value DESC" in captured[0][0]


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
        lambda *_args, **_kwargs: [
            {"id": 1, "username": "alice", "telegram_username": "alice_tg", "telegram_user_id": 123, "linked": 1, "link_state": "linked"}
        ],
    )

    response = mcp_server.handle_request(
        _req("tools/call", req_id=4, params={"name": "list_member_telegram_links", "arguments": {"include_unlinked": False, "limit": 10}})
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["count"] == 1
    assert payload["members"][0]["telegram_username"] == "alice_tg"
    assert payload["members"][0]["link_state"] == "linked"


def test_tools_call_list_member_telegram_links_rejects_out_of_range_limit():
    for limit in (0, 501, 999):
        response = mcp_server.handle_request(
            _req("tools/call", req_id=401, params={"name": "list_member_telegram_links", "arguments": {"limit": limit}})
        )
        assert response["error"]["code"] == -32602
        assert "limit must be between 1 and 500" in response["error"]["message"]


def test_tools_call_list_member_telegram_links_rejects_invalid_boolean():
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=402,
            params={"name": "list_member_telegram_links", "arguments": {"include_unlinked": "sometimes"}},
        )
    )
    assert response["error"]["code"] == -32602


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


def test_tools_call_create_member_rejects_invalid_admin_flag():
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=52,
            params={"name": "create_member", "arguments": {"username": "bob", "password": "secret", "is_admin": "maybe"}},
        )
    )
    assert response["error"]["code"] == -32602


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


def test_tools_call_create_proposal_rejects_invalid_basic_supplies_flag():
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=621,
            params={
                "name": "create_proposal",
                "arguments": {"title": "New printer", "amount": 10, "created_by": 1, "basic_supplies": "maybe"},
            },
        )
    )
    assert response["error"]["code"] == -32602




def test_tools_call_crreate_proposal_alias(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    monkeypatch.setattr(mcp_server, "_create_proposal_record", lambda *_args, **_kwargs: 78)
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=63,
            params={
                "name": "crreate_proposal",
                "arguments": {"title": "Keyboard", "amount": 45, "created_by": 1},
            },
        )
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["proposal_id"] == 78
    assert "Deprecated tool alias" in payload["warning"]



def test_tools_call_unknown_typo_tool_name_is_rejected():
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=64,
            params={"name": "creat_proposal", "arguments": {"title": "Keyboard", "amount": 45, "created_by": 1}},
        )
    )
    assert response["error"]["code"] == -32601

def test_tools_call_create_poll(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    monkeypatch.setattr(mcp_server.PollRepository, "create", lambda self, *_args, **_kwargs: 13)
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


def test_tools_call_accepts_tool_name_alias_for_name(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])
    monkeypatch.setattr(mcp_server.PollRepository, "create", lambda self, *_args, **_kwargs: 21)
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=212,
            params={
                "tool_name": "create_poll",
                "arguments": {"question": "Alias-based question", "options": ["A", "B"], "created_by": 1},
            },
        )
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["poll_id"] == 21


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


def test_tools_call_create_proposal_returns_integrity_error_code(monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda *_args, **_kwargs: [{"id": 1}])

    def _raise_integrity(*_args, **_kwargs):
        raise mcp_server.sqlite3.IntegrityError("constraint failed")

    monkeypatch.setattr(mcp_server, "_create_proposal_record", _raise_integrity)
    response = mcp_server.handle_request(
        _req(
            "tools/call",
            req_id=65,
            params={"name": "create_proposal", "arguments": {"title": "Desk", "amount": 10, "created_by": 1}},
        )
    )
    assert response["error"]["code"] == -32011


def test_process_jsonrpc_body_preserves_request_id_on_server_error(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise sqlite3.OperationalError("sensitive database detail")

    monkeypatch.setattr(mcp_server, "handle_request", _boom)
    status, payload = mcp_server._process_jsonrpc_body(json.dumps(_req("initialize", req_id=999)))
    body = json.loads(payload.decode("utf-8"))
    assert status == 500
    assert body["id"] == 999
    assert body["error"]["code"] == -32000
    assert body["error"]["message"] == "Internal server error"
    assert "sensitive database detail" not in payload.decode("utf-8")


def test_process_jsonrpc_body_batch_preserves_item_id_on_server_error(monkeypatch):
    def _boom(req, headers=None):
        if req.get("id") == 2:
            raise sqlite3.OperationalError("boom")
        return mcp_server._result(req.get("id"), {"ok": True})

    monkeypatch.setattr(mcp_server, "handle_request", _boom)
    status, payload = mcp_server._process_jsonrpc_body(
        json.dumps(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
            ]
        )
    )
    body = json.loads(payload.decode("utf-8"))
    assert status == 200
    assert body[0]["id"] == 1
    assert body[0]["result"]["ok"] is True
    assert body[1]["id"] == 2
    assert body[1]["error"]["code"] == -32000
