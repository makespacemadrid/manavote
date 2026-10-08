import json
import sqlite3

import pytest

from app.integrations import telegram_agent as agent
from app.integrations.assistant_safety import ModelLimits, SafetyRejection, history_groups, scrub


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    agent.configure_history_store(None)
    agent.configure_pending_action_store(None)
    agent.reset(901, 902)
    monkeypatch.setenv("OCABRA_CHAT_URL", "https://model.example/chat")
    for name in ("TELEGRAM_AGENT_CONTEXT_BUDGET", "TELEGRAM_AGENT_INPUT_BUDGET", "TELEGRAM_AGENT_OUTPUT_RESERVE"):
        monkeypatch.delenv(name, raising=False)
    yield
    agent.reset(901, 902)
    agent.configure_history_store(None)
    agent.configure_pending_action_store(None)


@pytest.mark.parametrize("value", ["0", "-1", "1.2", "", "abc", "１２", " 8"])
def test_invalid_budgets_rejected(monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_AGENT_INPUT_BUDGET", value)
    with pytest.raises(ValueError, match="TELEGRAM_AGENT_INPUT_BUDGET"):
        ModelLimits.from_env()


def test_incompatible_reserve_rejected(monkeypatch):
    monkeypatch.setenv("TELEGRAM_AGENT_CONTEXT_BUDGET", "5000")
    with pytest.raises(ValueError, match="must exceed"):
        ModelLimits.from_env()


def test_utf8_input_boundaries():
    limits = ModelLimits(input=4)
    limits.check_input("😀")
    with pytest.raises(SafetyRejection, match="input_budget_exceeded"):
        limits.check_input("😀a")


def test_complete_tool_group_trimming_and_exact_context_boundary():
    system = {"role": "system", "content": "actor policy"}
    current = [{"role": "user", "content": "current question"}]
    group = [{"role": "user", "content": "old question"},
             {"role": "assistant", "tool_calls": [{"id": "a"}, {"id": "b"}]},
             {"role": "tool", "tool_call_id": "a", "content": "large" * 400},
             {"role": "tool", "tool_call_id": "b", "content": "{}"}]
    base = ModelLimits()
    limits = ModelLimits(context=base.size([system, *current], []) + 10, output=10)
    assert limits.fit(system, group, current, []) == [system, *current]
    with pytest.raises(SafetyRejection, match="context_budget_exceeded"):
        ModelLimits(context=limits.context - 1, output=10).fit(system, [], current, [])
    assert history_groups(group) == [group]
    assert history_groups(group[1:]) == []
    assert history_groups(group[:-1]) == []


def test_scrub_sensitive_fields_urls_and_configured_values(monkeypatch):
    monkeypatch.setenv("OCABRA_API_KEY", "configured-private-value")
    value = {"description": "configured-private-value", "password": "unknown-password",
             "nested": '{"access_token":"private-token","amount":12}',
             "url": "https://user:private-pass@example.org/path?api_key=private-key&item=7",
             "safe": "https://shop.example/item?sku=9", "max_tokens": 20, "member_id": 3}
    cleaned = scrub(value)
    serialized = json.dumps(cleaned)
    for private in ("configured-private-value", "unknown-password", "private-token", "private-pass", "private-key"):
        assert private not in serialized
    assert cleaned["safe"] == value["safe"]
    assert cleaned["max_tokens"] == 20 and cleaned["member_id"] == 3
    assert json.loads(cleaned["nested"])["amount"] == 12
    assert "opaque-private" not in scrub("password='opaque-private' Bearer other-private")
    assert "other-private" not in scrub("Bearer other-private")


def test_oversized_or_secret_input_never_calls_model_or_changes_pending(monkeypatch):
    action = agent.PendingAction("create_poll", {"question": "Safe", "options": ["A", "B"]})
    agent._put_pending((901, 902), action)
    monkeypatch.setattr(agent.requests, "post", lambda *a, **k: pytest.fail("model called"))
    assert "más corta" in agent.answer(901, "a" * 4097, telegram_user_id=902, language_code="es")
    assert "credentials" in agent.answer(901, "password=private", telegram_user_id=902)
    assert agent._get_pending((901, 902)) == action
    assert agent._get_history((901, 902)) == []


class Response:
    def __init__(self, message):
        self.message = message
    def raise_for_status(self):
        pass
    def json(self):
        return {"choices": [{"message": self.message}]}


def test_all_rounds_bounded_and_tool_payload_scrubbed(monkeypatch):
    monkeypatch.setenv("OCABRA_API_KEY", "configured-private")
    payloads = []
    responses = iter([Response({"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "current_budget", "arguments": "{}"}}]}),
                      Response({"role": "assistant", "content": "budget 12 configured-private"})])
    def post(*a, **kwargs):
        payloads.append(kwargs["json"])
        return next(responses)
    monkeypatch.setattr(agent.requests, "post", post)
    monkeypatch.setattr(agent, "_call_mcp", lambda *a, **k: '{"budget":12,"password":"tool-private"}')
    reply = agent.answer(901, "budget?", telegram_user_id=902)
    assert "configured-private" not in reply
    assert len(payloads) == 2
    limits = ModelLimits.from_env()
    for payload in payloads:
        assert limits.size(payload["messages"], payload["tools"]) + payload["max_tokens"] <= limits.context
        assert "tool-private" not in json.dumps(payload)
    assert "configured-private" not in json.dumps(agent._get_history((901, 902)))
    assert "12" in reply


def test_large_tool_result_stops_before_next_model_round(monkeypatch):
    calls = []
    def post(*a, **k):
        calls.append(k)
        return Response({"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "current_budget", "arguments": "{}"}}]})
    monkeypatch.setattr(agent.requests, "post", post)
    monkeypatch.setattr(agent, "_call_mcp", lambda *a, **k: "x" * 40000)
    events = []
    reply = agent.answer(901, "budget?", telegram_user_id=902, on_event=lambda event, details: events.append((event, details)))
    assert "Previous actions" in reply
    assert len(calls) == 1
    assert events[-1][1]["reason_code"] == "context_budget_exceeded"


def test_model_invented_secret_in_allowed_action_does_not_reach_mcp_or_pending(monkeypatch):
    monkeypatch.setenv("OCABRA_API_KEY", "configured-private")
    monkeypatch.setattr(agent.requests, "post", lambda *a, **k: Response({"role": "assistant", "tool_calls": [
        {"id": "x", "function": {"name": "create_poll", "arguments": '{"question":"configured-private","options":["A","B"]}'}}]}))
    monkeypatch.setattr(agent, "_call_mcp", lambda *a, **k: pytest.fail("tool called"))
    assert "credentials" in agent.answer(901, "create a poll", is_admin=True, actor_member_id=1, telegram_user_id=902)
    assert agent._get_pending((901, 902)) is None


def test_persisted_history_scrubbed_before_write_and_on_read(tmp_path):
    path = tmp_path / "history.db"
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    conn = connect()
    conn.execute("CREATE TABLE telegram_conversation_history(chat_id INTEGER, telegram_user_id INTEGER, messages_json TEXT, updated_at REAL, PRIMARY KEY(chat_id, telegram_user_id))")
    conn.close()
    agent.configure_history_store(connect)
    agent._append_history((901, 902), [{"role": "user", "content": "password=private-history"}])
    conn = connect()
    assert "private-history" not in conn.execute("SELECT messages_json FROM telegram_conversation_history").fetchone()[0]
    conn.execute("UPDATE telegram_conversation_history SET messages_json=?", (json.dumps([{"role": "user", "content": "password=legacy-private"}]),))
    conn.commit()
    conn.close()
    assert "legacy-private" not in json.dumps(agent._get_history((901, 902)))
