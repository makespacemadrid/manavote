import json

from app.integrations import telegram_agent


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
                        "arguments": '{"question":"Choose?","options":["A","B"],"created_by":1}',
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

    reply = telegram_agent.answer(70, "Create a poll", telegram_user_id=7, is_admin=True)
    assert "/confirm" in reply
    assert calls == []

    confirmed = telegram_agent.answer(70, "/confirm", telegram_user_id=7, is_admin=True)
    assert "completed" in confirmed
    assert "Poll id: 9" in confirmed
    assert calls == [
        ("create_poll", {"question": "Choose?", "options": ["A", "B"], "created_by": 1})
    ]


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
    monkeypatch.setattr(telegram_agent.time, "monotonic", lambda: 161.0)
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
