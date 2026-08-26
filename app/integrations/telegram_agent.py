"""Natural-language Telegram agent backed by an OpenAI-compatible model and MCP.

The Telegram conversation pattern is inspired by Luis Rivera's ocabra_telegram:
https://github.com/luisriverag/ocabra_telegram
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import requests

from app import mcp_server


READ_ONLY_TOOLS = {
    "list_proposals",
    "current_budget",
    "get_voting_settings",
}
MUTATING_TOOLS = {"create_member", "create_proposal", "create_poll", "update_voting_settings"}
MAX_TOOL_ROUNDS = 4
ConversationKey = tuple[int, int]
_history: dict[ConversationKey, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=12))
_pending_actions: dict[ConversationKey, "PendingAction"] = {}
_state_lock = threading.RLock()


@dataclass(frozen=True)
class PendingAction:
    tool_name: str
    arguments: dict[str, Any]
    created_at: float = field(default_factory=time.monotonic)


def is_configured() -> bool:
    return bool(os.getenv("OCABRA_CHAT_URL", "").strip() and mcp_server.MCP_API_KEY)


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OCABRA_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _openai_tools(*, is_admin: bool) -> list[dict[str, Any]]:
    definitions = mcp_server._tool_definitions()
    if not is_admin:
        definitions = [item for item in definitions if item["name"] in READ_ONLY_TOOLS]
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["inputSchema"],
            },
        }
        for item in definitions
    ]


def _call_mcp(tool_name: str, arguments: dict[str, Any], *, is_admin: bool) -> str:
    allowed = {item["function"]["name"] for item in _openai_tools(is_admin=is_admin)}
    if tool_name not in allowed:
        return json.dumps({"error": "This Telegram account may not use that tool."})
    response = mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "telegram-agent",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
                "api_key": mcp_server.MCP_API_KEY,
            },
        }
    )
    if not response:
        return json.dumps({"error": "MCP returned no response."})
    if "error" in response:
        return json.dumps({"error": response["error"]["message"]})
    content = response.get("result", {}).get("content", [])
    return content[0].get("text", "{}") if content else "{}"


def _conversation_key(chat_id: int, telegram_user_id: int | None) -> ConversationKey:
    # Private chats normally use the same value for both IDs. Including the user
    # ID prevents one member in a group chat from seeing another member's context.
    return int(chat_id), int(telegram_user_id if telegram_user_id is not None else chat_id)


def _confirmation_text(action: PendingAction) -> str:
    return (
        f"⚠️ Please confirm MCP action {action.tool_name} with /confirm, "
        "or discard it with /cancel.\n"
        f"Arguments: {json.dumps(action.arguments, ensure_ascii=False, sort_keys=True)}"
    )


def _action_result_text(action: PendingAction, result: str) -> str:
    """Turn MCP JSON into a compact, Telegram-friendly completion message."""
    try:
        payload = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        payload = result
    if isinstance(payload, dict) and payload.get("error"):
        return f"❌ {action.tool_name} failed: {payload['error']}"
    if isinstance(payload, dict):
        details = "\n".join(
            f"{str(key).replace('_', ' ').capitalize()}: "
            f"{json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}"
            for key, value in payload.items()
        )
    else:
        details = str(payload)
    suffix = f"\n{details}" if details and details != "{}" else ""
    return f"✅ {action.tool_name} completed.{suffix}"


def answer(
    chat_id: int,
    text: str,
    *,
    telegram_user_id: int | None = None,
    is_admin: bool = False,
) -> str:
    """Answer natural language and let the model operate ManaVote through MCP tools."""
    url = os.getenv("OCABRA_CHAT_URL", "").strip()
    if not url:
        raise RuntimeError("Natural-language Telegram support is not configured.")

    key = _conversation_key(chat_id, telegram_user_id)
    normalized_text = text.strip().lower()
    with _state_lock:
        pending = _pending_actions.get(key)
    if normalized_text in {"/cancel", "cancel"}:
        with _state_lock:
            removed = _pending_actions.pop(key, None)
        return "✅ Pending action cancelled." if removed else "There is no pending action to cancel."
    if normalized_text in {"/confirm", "confirm"}:
        if not pending:
            return "There is no pending action to confirm."
        confirmation_ttl = float(os.getenv("TELEGRAM_CONFIRM_TTL_SECONDS", "300"))
        if time.monotonic() - pending.created_at > confirmation_ttl:
            with _state_lock:
                _pending_actions.pop(key, None)
            return "⌛ That pending action expired. Please request it again."
        if not is_admin:
            with _state_lock:
                _pending_actions.pop(key, None)
            return "❌ Only a linked administrator can confirm that action."
        result = _call_mcp(pending.tool_name, pending.arguments, is_admin=True)
        with _state_lock:
            _pending_actions.pop(key, None)
        return _action_result_text(pending, result)

    with _state_lock:
        history_snapshot = list(_history[key])
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": os.getenv(
                "TELEGRAM_AGENT_SYSTEM_PROMPT",
                "You are the ManaVote Telegram assistant. Use the supplied tools for ManaVote facts and actions. "
                "Never invent tool results. If a tool says confirmation_required, repeat its confirmation message "
                "and do not claim the action succeeded. Reply concisely in the user's language using plain text "
                "that reads well in Telegram.",
            ),
        },
        *history_snapshot,
        {"role": "user", "content": text},
    ]
    tools = _openai_tools(is_admin=is_admin)

    for _ in range(MAX_TOOL_ROUNDS):
        response = requests.post(
            url,
            headers=_headers(),
            json={
                "model": os.getenv("OCABRA_MODEL", "ocabra"),
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.2,
                "stream": False,
            },
            timeout=float(os.getenv("OCABRA_TIMEOUT_SECONDS", "60")),
        )
        response.raise_for_status()
        assistant = response.json()["choices"][0]["message"]
        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            reply = (assistant.get("content") or "I couldn't produce a response.").strip()
            with _state_lock:
                _history[key].extend(
                    ({"role": "user", "content": text}, {"role": "assistant", "content": reply})
                )
            return reply

        messages.append(assistant)
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except (TypeError, json.JSONDecodeError):
                arguments = {}
            if not isinstance(arguments, dict):
                result = json.dumps({"error": "Tool arguments must be a JSON object."})
            elif function.get("name") in MUTATING_TOOLS:
                action = PendingAction(function["name"], arguments)
                with _state_lock:
                    _pending_actions[key] = action
                # Do not rely on the model to reproduce a safety prompt. Return
                # the exact confirmation instructions immediately and avoid an
                # unnecessary second model round.
                return _confirmation_text(action)
            else:
                result = _call_mcp(function.get("name", ""), arguments, is_admin=is_admin)
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.get("id", ""), "content": result}
            )

    raise RuntimeError("The assistant exceeded the MCP tool-call limit.")


def reset(chat_id: int, telegram_user_id: int | None = None) -> None:
    key = _conversation_key(chat_id, telegram_user_id)
    with _state_lock:
        _history.pop(key, None)
        _pending_actions.pop(key, None)
