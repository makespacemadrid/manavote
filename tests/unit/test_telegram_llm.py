import json

from app.integrations.telegram_llm import ConversationStore, UpdateDeduplicator, run_telegram_assistant


class MCP:
    def __init__(self):
        self.calls = []

    def list_tools(self):
        return [{"name": "current_budget", "description": "Read budget", "inputSchema": {"type": "object"}}]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": '{"budget": 250}'}]}


class LLM:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def complete(self, messages, tools=None):
        self.requests.append((list(messages), tools))
        return next(self.replies)


def test_plain_language_can_select_mcp_tool_and_explain_result():
    llm = LLM([
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call-1", "type": "function",
            "function": {"name": "current_budget", "arguments": "{}"},
        }]},
        {"role": "assistant", "content": "The current budget is €250."},
    ])
    mcp = MCP()

    result = run_telegram_assistant("How much money is available?", llm_client=llm, mcp_client=mcp)

    assert result == "The current budget is €250."
    assert mcp.calls == [("current_budget", {})]
    assert llm.requests[0][1][0]["function"]["name"] == "current_budget"
    tool_message = llm.requests[1][0][-1]
    assert tool_message == {"role": "tool", "tool_call_id": "call-1", "content": '{"budget": 250}'}


def test_answer_without_tool_is_returned_directly():
    llm = LLM([{"role": "assistant", "content": "Hello! How can I help?"}])
    assert run_telegram_assistant("hello", llm_client=llm, mcp_client=MCP()) == "Hello! How can I help?"


def test_invalid_model_tool_arguments_are_reported_back_to_model():
    llm = LLM([
        {"role": "assistant", "tool_calls": [{"id": "bad", "function": {"name": "current_budget", "arguments": "[]"}}]},
        {"role": "assistant", "content": "I couldn't run that tool."},
    ])
    result = run_telegram_assistant("budget?", llm_client=llm, mcp_client=MCP())
    assert result == "I couldn't run that tool."
    assert "Tool error" in llm.requests[1][0][-1]["content"]


def test_write_tool_is_blocked_until_confirmation_is_granted():
    tool_call = {"role": "assistant", "tool_calls": [{
        "id": "write", "function": {"name": "create_poll", "arguments": '{"question":"Lunch?"}'},
    }]}
    llm = LLM([tool_call, {"role": "assistant", "content": "Please confirm before I create it."}])
    mcp = MCP()
    blocked = []
    result = run_telegram_assistant(
        "Create a poll", llm_client=llm, mcp_client=mcp,
        on_write_blocked=lambda name, arguments: blocked.append((name, arguments)),
    )
    assert result == "Please confirm before I create it."
    assert mcp.calls == []
    assert blocked == [("create_poll", {"question": "Lunch?"})]
    assert "confirmation required" in llm.requests[1][0][-1]["content"]


def test_write_tool_runs_after_explicit_confirmation():
    class WriteMCP(MCP):
        def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return {"content": [{"type": "text", "text": "created"}]}

    llm = LLM([
        {"role": "assistant", "tool_calls": [{
            "id": "write", "function": {"name": "create_poll", "arguments": '{"question":"Lunch?"}'},
        }]},
        {"role": "assistant", "content": "The poll was created."},
    ])
    mcp = WriteMCP()
    result = run_telegram_assistant(
        "confirm", llm_client=llm, mcp_client=mcp,
        history=[{"role": "assistant", "content": "Please confirm the new poll."}],
        approved_write={"name": "create_poll", "arguments": {"question": "Lunch?"}},
    )
    assert result == "The poll was created."
    assert mcp.calls == [("create_poll", {"question": "Lunch?"})]


def test_conversation_store_keeps_bounded_history_and_can_reset():
    store = ConversationStore(max_messages=2)
    store.append_exchange(5, "first", "one")
    store.append_exchange(5, "second", "two")
    assert store.get(5) == [{"role": "user", "content": "second"}, {"role": "assistant", "content": "two"}]
    store.clear(5)
    assert store.get(5) == []


def test_confirmation_is_bound_to_exact_tool_arguments():
    llm = LLM([
        {"role": "assistant", "tool_calls": [{
            "id": "changed", "function": {"name": "create_poll", "arguments": '{"question":"Different?"}'},
        }]},
        {"role": "assistant", "content": "That changed, so please confirm again."},
    ])
    mcp = MCP()
    blocked = []
    result = run_telegram_assistant(
        "confirm", llm_client=llm, mcp_client=mcp,
        approved_write={"name": "create_poll", "arguments": {"question": "Lunch?"}},
        on_write_blocked=lambda name, arguments: blocked.append((name, arguments)),
    )
    assert result == "That changed, so please confirm again."
    assert mcp.calls == []
    assert blocked == [("create_poll", {"question": "Different?"})]


def test_unknown_future_tool_is_fail_safe_and_requires_confirmation():
    llm = LLM([
        {"role": "assistant", "tool_calls": [{
            "id": "future", "function": {"name": "archive_proposal", "arguments": '{"id":7}'},
        }]},
        {"role": "assistant", "content": "Please confirm archiving proposal 7."},
    ])
    mcp = MCP()
    result = run_telegram_assistant("archive 7", llm_client=llm, mcp_client=mcp)
    assert "confirm" in result.lower()
    assert mcp.calls == []


def test_conversation_store_expires_and_clears_pending_write():
    store = ConversationStore(ttl_seconds=0)
    store.set_pending_write(5, "create_poll", {"question": "Lunch?"})
    assert store.get_pending_write(5) is None
    store = ConversationStore()
    store.set_pending_write(5, "create_poll", {"question": "Lunch?"})
    assert store.get_pending_write(5) == {"name": "create_poll", "arguments": {"question": "Lunch?"}}
    store.clear(5)
    assert store.get_pending_write(5) is None


def test_update_deduplicator_claims_each_update_once_and_bounds_memory():
    updates = UpdateDeduplicator(max_updates=2)
    assert updates.claim(100) is True
    assert updates.claim(100) is False
    assert updates.claim(101) is True
    assert updates.claim(102) is True
    # The oldest claim was evicted when the bounded store filled.
    assert updates.claim(100) is True


def test_update_without_id_is_not_deduplicated():
    updates = UpdateDeduplicator()
    assert updates.claim(None) is True
    assert updates.claim(None) is True
