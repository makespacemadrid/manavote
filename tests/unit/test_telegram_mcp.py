import json

from app.integrations.telegram_mcp import run_telegram_mcp_command


class Client:
    def list_tools(self):
        return [{"name": "budget", "description": "Read budget"}]

    def call_tool(self, name, arguments):
        return {"content": [{"type": "text", "text": f"{name}: {arguments['limit']}"}]}


def context(text, user_id=5, chat_type="private"):
    return {"text": text, "telegram_user_id": user_id, "chat_type": chat_type}


def test_rejects_users_outside_explicit_allowlist():
    result = run_telegram_mcp_command(context("/mcp tools"), client=Client(), allowed_user_ids=set())
    assert "not allowed" in result


def test_rejects_group_chat_by_default():
    result = run_telegram_mcp_command(
        context("/mcp tools", chat_type="group"), client=Client(), allowed_user_ids={"5"}
    )
    assert "private chat" in result


def test_lists_tools_and_unwraps_tool_text_result():
    listed = run_telegram_mcp_command(context("/mcp tools"), client=Client(), allowed_user_ids={"5"})
    called = run_telegram_mcp_command(
        context('/mcp call budget {"limit":2}'), client=Client(), allowed_user_ids={"5"}
    )
    assert "/mcp budget" in listed
    assert "Read budget" in listed
    assert called == "budget: 2"


def test_rejects_non_object_arguments_before_calling_tool():
    result = run_telegram_mcp_command(context("/mcp call budget []"), client=Client(), allowed_user_ids={"5"})
    assert "Arguments must be a JSON object" in result


def test_bare_mcp_lists_copyable_commands():
    result = run_telegram_mcp_command(context("/mcp"), client=Client(), allowed_user_ids={"5"})
    assert "/mcp budget" in result


def test_short_tool_form_accepts_friendly_key_value_arguments():
    result = run_telegram_mcp_command(
        context("/mcp budget limit=2"), client=Client(), allowed_user_ids={"5"}
    )
    assert result == "budget: 2"


def test_friendly_arguments_support_quoted_strings_and_typed_values():
    class CapturingClient(Client):
        def call_tool(self, name, arguments):
            return arguments

    result = run_telegram_mcp_command(
        context('/mcp search query="active proposals" limit=5 enabled=true'),
        client=CapturingClient(),
        allowed_user_ids={"5"},
    )
    assert json.loads(result) == {"query": "active proposals", "limit": 5, "enabled": True}
