import json
import sqlite3

import pytest

from app.integrations import telegram_agent


@pytest.fixture(autouse=True)
def use_in_memory_pending_actions():
    telegram_agent.configure_pending_action_store(None)
    telegram_agent.configure_history_store(None)
    yield
    telegram_agent.configure_pending_action_store(None)
    telegram_agent.configure_history_store(None)


class FakeResponse:
    def __init__(self, message):
        self.message = message

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": self.message}]}


def test_non_admin_tools_include_member_feedback_only_as_a_write():
    names = {tool["function"]["name"] for tool in telegram_agent._openai_tools(is_admin=False)}
    assert names == telegram_agent.READ_ONLY_TOOLS | telegram_agent.MEMBER_WRITABLE_TOOLS
    assert "create_member" not in names
    assert "list_member_telegram_links" not in names
    assert "list_user_statistics" not in names
    assert "list_polls" in names
    assert "list_group_purchases" in names


def test_feedback_tool_hides_member_attribution_from_model():
    tools = telegram_agent._openai_tools(is_admin=False, actor_member_id=42)
    feedback = next(tool["function"] for tool in tools if tool["function"]["name"] == "create_feedback")
    assert "member_id" not in feedback["parameters"]["properties"]
    assert "member_id" not in feedback["parameters"]["required"]


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
            schema_fingerprint TEXT, arguments_digest TEXT,
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


def test_conversation_history_survives_worker_instances_and_stays_bounded(tmp_path):
    db_path = tmp_path / "history.db"

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    conn = connect()
    conn.execute(
        """
        CREATE TABLE telegram_conversation_history (
            chat_id INTEGER NOT NULL, telegram_user_id INTEGER NOT NULL,
            messages_json TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY (chat_id, telegram_user_id)
        )
        """
    )
    conn.commit()
    conn.close()
    telegram_agent.configure_history_store(connect)
    key = (100, 200)

    assert telegram_agent._get_history(key) == []

    telegram_agent._append_history(
        key, [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    )
    # A second "worker" (a fresh connection) must see what the first one wrote.
    assert telegram_agent._get_history(key) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    for i in range(telegram_agent.MAX_HISTORY_MESSAGES):
        telegram_agent._append_history(key, [{"role": "user", "content": f"msg-{i}"}])

    history = telegram_agent._get_history(key)
    assert len(history) == telegram_agent.MAX_HISTORY_MESSAGES
    assert history[-1] == {"role": "user", "content": f"msg-{telegram_agent.MAX_HISTORY_MESSAGES - 1}"}
    assert {"role": "user", "content": "hi"} not in history

    telegram_agent._clear_history(key)
    assert telegram_agent._get_history(key) == []


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


def test_agent_reports_model_latency_and_tool_names(monkeypatch):
    responses = iter(
        [
            FakeResponse(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {"name": "current_budget", "arguments": "{}"},
                        }
                    ],
                }
            ),
            FakeResponse({"role": "assistant", "content": "€100"}),
        ]
    )
    events = []
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    monkeypatch.setattr(telegram_agent.requests, "post", lambda *_a, **_kw: next(responses))
    monkeypatch.setattr(telegram_agent, "_call_mcp", lambda *_a, **_kw: "{}")

    telegram_agent.answer(56, "Budget?", on_event=lambda event, details: events.append((event, details)))

    assert [event for event, _details in events] == [
        "model_request_completed",
        "tool_call_received",
        "model_request_completed",
    ]
    assert events[0][1]["model_round"] == 1
    assert events[0][1]["model_latency_ms"] >= 0
    assert events[1][1] == {"tool_name": "current_budget"}


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


def test_confirm_rejects_tampered_arguments_digest(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(82, 8)
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction(
            "create_poll", {"question": "Choose?"}, arguments_digest="not-the-real-digest"
        )
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("tampered action ran")),
    )

    reply = telegram_agent.answer(82, "/confirm", telegram_user_id=8, is_admin=True)

    assert "changed unexpectedly" in reply.lower()
    with telegram_agent._state_lock:
        assert key not in telegram_agent._pending_actions


def test_confirm_rejects_changed_tool_schema(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(83, 8)
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction(
            "create_poll", {}, schema_fingerprint="stale-fingerprint-from-a-different-version"
        )
    monkeypatch.setattr(
        telegram_agent,
        "_call_mcp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("stale-schema action ran")),
    )

    reply = telegram_agent.answer(83, "/confirm", telegram_user_id=8, is_admin=True)

    assert "no longer available" in reply.lower()


def test_confirm_accepts_matching_digest_and_schema(monkeypatch):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(84, 8)
    arguments = {"question": "Choose?", "options": ["A", "B"], "created_by": 1}
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction(
            "create_poll",
            arguments,
            schema_fingerprint=telegram_agent._schema_fingerprint("create_poll"),
            arguments_digest=telegram_agent._stable_digest(arguments),
        )
    monkeypatch.setattr(telegram_agent, "_call_mcp", lambda *_args, **_kwargs: '{"poll_id": 5}')

    reply = telegram_agent.answer(84, "/confirm", telegram_user_id=8, is_admin=True)

    assert "completed" in reply.lower()


def test_mutation_lifecycle_emits_reason_coded_audit_events(monkeypatch, caplog):
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
                        "arguments": '{"question":"Choose?","options":["A","B"]}',
                    },
                }
            ],
        }
    )
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    monkeypatch.setattr(telegram_agent.requests, "post", lambda *_a, **_kw: response)
    monkeypatch.setattr(telegram_agent, "_call_mcp", lambda *_args, **_kwargs: '{"poll_id": 9}')

    with caplog.at_level("INFO", logger="app.integrations.telegram_agent"):
        telegram_agent.answer(85, "Create a poll", telegram_user_id=8, actor_member_id=1, is_admin=True)
        telegram_agent.answer(85, "/confirm", telegram_user_id=8, actor_member_id=1, is_admin=True)

    events = [
        json.loads(record.message.split("telegram_assistant_mutation ", 1)[1])
        for record in caplog.records
        if record.message.startswith("telegram_assistant_mutation ")
    ]
    assert [event["event"] for event in events] == ["proposed", "confirmed", "completed"]
    assert all(event["tool_name"] == "create_poll" for event in events)
    assert events[0]["reason_code"] == "ok"
    assert events[-1]["reason_code"] == "ok"


def test_cancel_and_reset_emit_cancelled_audit_events(monkeypatch, caplog):
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://ocabra.example/v1/chat/completions")
    key = telegram_agent._conversation_key(86, 8)
    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction("create_poll", {})

    with caplog.at_level("INFO", logger="app.integrations.telegram_agent"):
        telegram_agent.answer(86, "/cancel", telegram_user_id=8, is_admin=True)

    with telegram_agent._state_lock:
        telegram_agent._pending_actions[key] = telegram_agent.PendingAction("create_poll", {})
    with caplog.at_level("INFO", logger="app.integrations.telegram_agent"):
        telegram_agent.reset(86, 8)

    events = [
        json.loads(record.message.split("telegram_assistant_mutation ", 1)[1])
        for record in caplog.records
        if record.message.startswith("telegram_assistant_mutation ")
    ]
    reason_codes = [event["reason_code"] for event in events if event["event"] == "cancelled"]
    assert "user_cancelled" in reason_codes
    assert "reset_command" in reason_codes


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
