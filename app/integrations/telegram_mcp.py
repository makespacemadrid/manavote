"""Telegram-facing parsing and formatting for the MCP bridge."""

import json
import shlex

from app.integrations.mcp_client import MCPClientError

HELP_TEXT = (
    "MCP commands:\n"
    "/mcp — show available tools\n"
    "/mcp <tool> [key=value ...]\n"
    "/mcp call <tool> [JSON object]\n\n"
    "Examples:\n"
    "/mcp current_budget\n"
    "/mcp list_proposals status=active limit=5"
)
MAX_TELEGRAM_TEXT = 4000


def _format_tool_result(result):
    """Prefer MCP text content over dumping its transport envelope."""
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        parts = [item.get("text") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        if parts:
            return "\n".join(parts)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _parse_arguments(raw):
    """Accept either a JSON object or friendly shell-style key=value pairs."""
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith(("{", "[")):
        arguments = json.loads(raw)
        if not isinstance(arguments, dict):
            raise ValueError("Arguments must be a JSON object.")
        return arguments

    arguments = {}
    for token in shlex.split(raw):
        if "=" not in token:
            raise ValueError(f"Expected key=value, got: {token}")
        key, value = token.split("=", 1)
        if not key or key in arguments:
            raise ValueError(f"Invalid or duplicate argument: {key or token}")
        try:
            arguments[key] = json.loads(value)
        except json.JSONDecodeError:
            arguments[key] = value
    return arguments


def _list_tools(client):
    tools = client.list_tools()
    if not tools:
        return "No MCP tools are currently available."
    lines = ["Available MCP tools (tap or copy a command):"]
    for tool in tools:
        description = tool.get("description", "").strip()
        lines.append(f"• /mcp {tool['name']}" + (f"\n  {description}" if description else ""))
    return "\n".join(lines)


def run_telegram_mcp_command(message_ctx, *, client, allowed_user_ids, allow_group_chats=False):
    """Validate authorization and execute one Telegram MCP command."""
    user_id = message_ctx.get("telegram_user_id")
    if user_id is None or str(user_id) not in allowed_user_ids:
        return "❌ You are not allowed to use MCP tools."
    if not allow_group_chats and message_ctx.get("chat_type") not in {None, "private"}:
        return "❌ MCP commands are only available in a private chat with the bot."

    parts = (message_ctx.get("text") or "").split(maxsplit=2)
    if len(parts) < 2:
        try:
            return _list_tools(client)
        except MCPClientError as exc:
            return f"❌ MCP request failed: {exc}"
    if parts[1].lower() == "help":
        return HELP_TEXT
    try:
        if parts[1].lower() == "tools" and len(parts) == 2:
            response = _list_tools(client)
        else:
            if parts[1].lower() == "call":
                if len(parts) < 3:
                    return f"❌ Choose a tool.\n\n{HELP_TEXT}"
                call_parts = parts[2].split(maxsplit=1)
                tool_name = call_parts[0]
                raw_arguments = call_parts[1] if len(call_parts) == 2 else ""
            else:
                tool_name = parts[1]
                raw_arguments = parts[2] if len(parts) == 3 else ""
            arguments = _parse_arguments(raw_arguments)
            response = _format_tool_result(client.call_tool(tool_name, arguments))
    except json.JSONDecodeError:
        return "❌ Arguments must be a valid JSON object."
    except ValueError as exc:
        return f"❌ {exc}\nTry /mcp help for examples."
    except MCPClientError as exc:
        return f"❌ MCP request failed: {exc}"
    return response if len(response) <= MAX_TELEGRAM_TEXT else response[: MAX_TELEGRAM_TEXT - 3] + "..."
