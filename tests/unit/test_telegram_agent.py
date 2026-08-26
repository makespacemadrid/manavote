import json
import sqlite3

import pytest

from app.integrations import telegram_agent


@pytest.fixture(autouse=True)
def use_in_memory_pending_actions():
    telegram_agent.configure_pending_action_store(None)
    yield
    telegram_agent.configure_pending_action_store(None)


class FakeResponse:
    def __init__(self, message):
        self.message = message

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": self.message}]}


def test_non_admin_tools_are_read_only():
    names = {tool["function"]["name"] for tool in telegram_agent._openai_tools(is_admin=False)}
    assert names == telegram_agent.READ_ONLY_TOOLS
    assert "create_member" not in names
    assert "list_member_telegram_links" not in names
    assert "list_user_statistics" not in names
    assert "list_polls" in names
    assert "list_group_purchases" in names


def test_admin_tools_exclude_password_bearing_member_creation():
    tools = telegram_agent._openai_tools(is_admin=True)
    names = {tool["function"]["name"] for tool in tools}

    assert names == telegram_agent.TELEGRAM_TOOLS
    assert "create_member" not in names
    assert all("password" not in json.dumps(tool).lower() for tool in tools)

    statistics = next(tool for tool in tools if tool["function"]["name"] == "list_user_statistics")
    properties = statistics["function"]["parameters"]["properties"]
    assert "username" in properties
    assert "approved_budget_percentage" in properties["sort_by"]["enum"]
    assert "average_votes_per_created_poll" in properties["sort_by"]["enum"]
    assert "created_group_purchase_order_value" in properties["sort_by"]["enum"]


def test_password_bearing_tool_is_denied_before_mcp_call(monkeypatch):
    monkeypatch.setattr(
        telegram_agent.mcp_server,
        "handle_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("MCP should not be called")),
    )

    result = json.loads(
        telegram_agent._call_mcp(
            "create_member",
            {"username": "member", "password": "do-not-leak"},
            is_admin=True,
        )
    )

    assert result == {"error": "This Telegram account may not use that tool."}
    assert "do-not-leak" not in json.dumps(result)


def test_confirmation_redacts_unexpected_nested_secret_arguments():
    action = telegram_agent.PendingAction(
        "create_poll",
        {
            "question": "Choose?",
            "metadata": {"access_token": "hidden-token", "label": "safe"},
            "options": [{"api_key": "hidden-key"}],
        },
    )

    text = telegram_agent._confirmation_text(action)

    assert "hidden-token" not in text
    assert "hidden-key" not in text
    assert text.count("[REDACTED]") == 2
    assert '"label": "safe"' in text


def test_pending_actions_survive_worker_instances_and_are_consumed_atomically(tmp_path):
    db_path = tmp_path / "pending.db"

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    conn = connect()
    conn.execute(
        """
        CREATE TABLE telegram_pending_actions (
            chat_id INTEGER NOT NULL, telegram_user_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL, arguments_json TEXT NOT NULL,
            actor_member_id INTEGER, created_at REAL NOT NULL,
            PRIMARY KEY (chat_id, telegram_user_id)
        )
        """
    )
    conn.commit()
    conn.close()
    telegram_agent.configure_pending_action_store(connect)
    key = (100, 200)
    action = telegram_agent.PendingAction(
        "create_proposal", {"title": "Shared state", "amount": 10}, actor_member_id=3
    )

    telegram_agent._put_pending(key, action)

    assert telegram_agent._get_pending(key) == action
    assert telegram_agent._pop_pending(key) == action
    assert telegram_agent._pop_pending(key) is None


def test_agent_executes_mcp_tool_and_returns_model_answer(monkeypatch):
    responses = iter(
        [
            FakeResponse(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "current_budget", "arguments": "{}"},
                        }
                    ],
                }
            ),
            FakeResponse({"role": "assistant", "content": "The budget is €100."}),
        ]
    )
    payloads = []

    def fake_post(*_args, **kwargs):
        payloads.append(kwargs["json"])
        return next(responses)

    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    monkeypatch.setattr(telegram_agent.requests, "post", fake_post)
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda name, arguments, **_kwargs: json.dumps({"budget": 100}),
    )
    telegram_agent.reset(55)

    assert telegram_agent.answer(55, "What's our budget?") == "The budget is €100."
    assert payloads[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"budget": 100}',
    }


def test_disallowed_mcp_tool_is_not_called(monkeypatch):
    monkeypatch.setattr(telegram_agent, "_openai_tools", lambda **_kwargs: [])
    assert "may not use" in telegram_agent._call_mcp("create_member", {}, is_admin=False)


def test_mutating_tool_waits_for_explicit_confirmation(monkeypatch):
    response = FakeResponse(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "create-1",
                    "type": "function",
                    "function": {
                        "name": "create_poll",
                        "arguments": '{"question":"Choose?","options":["A","B"],"created_by":999,"password":"drop-me"}',
                    },
                }
            ],
        }
    )
    calls = []
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    monkeypatch.setattr(telegram_agent.requests, "post", lambda *_a, **_kw: response)
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda name, arguments, **_kwargs: calls.append((name, arguments)) or '{"poll_id": 9}',
    )
    telegram_agent.reset(70, 7)

    reply = telegram_agent.answer(
        70, "Create a poll", telegram_user_id=7, actor_member_id=42, is_admin=True
    )
    assert "/confirm" in reply
    assert calls == []

    confirmed = telegram_agent.answer(
        70, "/confirm", telegram_user_id=7, actor_member_id=42, is_admin=True
    )
    assert "completed" in confirmed
    assert "Poll id: 9" in confirmed
    assert calls == [
        ("create_poll", {"question": "Choose?", "options": ["A", "B"], "created_by": 42})
    ]


def test_group_command_mention_confirms_pending_action(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(70, 7)
    telegram_agent._put_pending(
        key,
        telegram_agent.PendingAction(
            "create_poll", {"question": "Choose?", "options": ["A", "B"]}, actor_member_id=42
        ),
    )
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda *_args, **_kwargs: '{"poll_id": 9}',
    )

    reply = telegram_agent.answer(
        70,
        "/confirm@manavote_bot",
        telegram_user_id=7,
        actor_member_id=42,
        is_admin=True,
    )

    assert "create_poll completed" in reply
    assert "Poll id: 9" in reply


def test_group_command_mention_cancels_pending_action(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(80, 8)
    telegram_agent._put_pending(key, telegram_agent.PendingAction("create_poll", {}))

    reply = telegram_agent.answer(
        80, "/cancel@manavote_bot", telegram_user_id=8, is_admin=True
    )

    assert reply == "✅ Pending action cancelled."
    assert telegram_agent._get_pending(key) is None


def test_create_tool_schemas_bind_creator_to_linked_member():
    tools = telegram_agent._openai_tools(is_admin=True, actor_member_id=42)
    create_tools = {
        tool["function"]["name"]: tool["function"]
        for tool in tools
        if tool["function"]["name"] in {"create_proposal", "create_poll"}
    }

    assert create_tools.keys() == {"create_proposal", "create_poll"}
    for function in create_tools.values():
        assert "created_by" not in function["parameters"]["properties"]
        assert "created_by" not in function["parameters"]["required"]
        assert "linked Telegram member" in function["description"]


def test_confirmed_proposal_notifies_group(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(71, 7)
    action = telegram_agent.PendingAction(
        "create_proposal",
        {"title": "New lathe", "amount": 500, "created_by": 42},
        actor_member_id=42,
    )
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = action
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda *_args, **_kwargs: '{"success":true,"proposal_id":77}',
    )
    notifications = []

    reply = telegram_agent.answer(
        71,
        "/confirm",
        telegram_user_id=7,
        actor_member_id=42,
        is_admin=True,
        on_proposal_created=lambda proposal_id, arguments: notifications.append(
            (proposal_id, arguments)
        )
        or True,
    )

    assert "completed" in reply
    assert notifications == [(77, action.arguments)]


def test_confirmed_proposal_reports_group_notification_failure(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(72, 7)
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction(
            "create_proposal", {"title": "New lathe", "amount": 500}, actor_member_id=42
        )
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda *_args, **_kwargs: '{"success":true,"proposal_id":78}',
    )

    reply = telegram_agent.answer(
        72,
        "/confirm",
        telegram_user_id=7,
        actor_member_id=42,
        is_admin=True,
        on_proposal_created=lambda *_args: False,
    )

    assert "proposal was saved" in reply
    assert "notification could not be sent" in reply


def test_pending_actions_are_isolated_between_group_chat_users(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(80, 8)
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction("create_poll", {})

    assert "no pending action" in telegram_agent.answer(
        80, "/confirm", telegram_user_id=9, is_admin=True
    ).lower()
    assert "pending action cancelled" in telegram_agent.answer(
        80, "/cancel", telegram_user_id=8, is_admin=True
    ).lower()


def test_pending_action_confirmation_expires(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    monkeypatch.setenv("TELEGRAM_CONFIRM_TTL_SECONDS", "60")
    key = telegram_agent._conversation_key(81, 8)
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction(
            "create_poll", {}, created_at=100.0
        )
    monkeypatch.setattr(telegram_agent.time, "time", lambda: 161.0)
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("expired action ran")),
    )

    reply = telegram_agent.answer(81, "/confirm", telegram_user_id=8, is_admin=True)
    assert "expired" in reply.lower()
    with telegram_agent._state_lock:
        assert key not in telegram_agent._pending_actions


def test_array_tool_arguments_are_rejected(monkeypatch):
    responses = iter(
        [
            FakeResponse(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "bad-1",
                            "type": "function",
                            "function": {"name": "current_budget", "arguments": "[]"},
                        }
                    ],
                }
            ),
            FakeResponse({"role": "assistant", "content": "The tool arguments were invalid."}),
        ]
    )
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    monkeypatch.setattr(telegram_agent.requests, "post", lambda *_a, **_kw: next(responses))
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("MCP should not be called")),
    )

    assert "invalid" in telegram_agent.answer(90, "Budget?", telegram_user_id=9).lower()


def test_action_result_formats_mcp_errors_for_users():
    action = telegram_agent.PendingAction("create_poll", {})
    assert telegram_agent._action_result_text(action, '{"error":"database unavailable"}') == (
        "❌ create_poll failed: database unavailable"
    )
