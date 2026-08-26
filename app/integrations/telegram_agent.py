"""Natural-language Telegram agent backed by an OpenAI-compatible model and MCP.

The Telegram conversation pattern is inspired by Luis Rivera's ocabra_telegram:
https://github.com/luisriverag/ocabra_telegram
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from app import mcp_server


READ_ONLY_TOOLS = {
    "list_proposals",
    "list_polls",
    "list_group_purchases",
    "current_budget",
    "get_voting_settings",
}
ADMIN_READ_ONLY_TOOLS = {"list_member_telegram_links", "list_user_statistics"}
MUTATING_TOOLS = {"create_proposal", "create_poll", "update_voting_settings"}
# Tools are deliberately classified here instead of granting administrators every
# MCP tool. In particular, create_member accepts a password and must never be
# exposed to a model-backed Telegram conversation.
TELEGRAM_TOOLS = READ_ONLY_TOOLS | ADMIN_READ_ONLY_TOOLS | MUTATING_TOOLS
MAX_TOOL_ROUNDS = 4
ConversationKey = tuple[int, int]
_history: dict[ConversationKey, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=12))
_pending_actions: dict[ConversationKey, "PendingAction"] = {}
_pending_connection_factory: Callable[[], Any] | None = None
_state_lock = threading.RLock()


@dataclass(frozen=True)
class PendingAction:
    tool_name: str
    arguments: dict[str, Any]
    actor_member_id: int | None = None
    created_at: float = field(default_factory=time.time)


def configure_pending_action_store(connection_factory: Callable[[], Any] | None) -> None:
    """Use a shared database for confirmations, or memory when factory is ``None``."""
    global _pending_connection_factory
    _pending_connection_factory = connection_factory


def _pending_from_row(row: Any) -> PendingAction:
    return PendingAction(
        tool_name=str(row["tool_name"]),
        arguments=json.loads(row["arguments_json"]),
        actor_member_id=row["actor_member_id"],
        created_at=float(row["created_at"]),
    )


def _get_pending(key: ConversationKey) -> PendingAction | None:
    if _pending_connection_factory is None:
        with _state_lock:
            return _pending_actions.get(key)
    conn = _pending_connection_factory()
    try:
        row = conn.execute(
            "SELECT tool_name, arguments_json, actor_member_id, created_at "
            "FROM telegram_pending_actions WHERE chat_id = ? AND telegram_user_id = ?",
            key,
        ).fetchone()
        return _pending_from_row(row) if row else None
    finally:
        conn.close()


def _put_pending(key: ConversationKey, action: PendingAction) -> None:
    if _pending_connection_factory is None:
        with _state_lock:
            _pending_actions[key] = action
        return
    conn = _pending_connection_factory()
    try:
        conn.execute(
            """
            INSERT INTO telegram_pending_actions
                (chat_id, telegram_user_id, tool_name, arguments_json, actor_member_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, telegram_user_id) DO UPDATE SET
                tool_name = excluded.tool_name,
                arguments_json = excluded.arguments_json,
                actor_member_id = excluded.actor_member_id,
                created_at = excluded.created_at
            """,
            (*key, action.tool_name, json.dumps(action.arguments), action.actor_member_id, action.created_at),
        )
        conn.commit()
    finally:
        conn.close()


def _pop_pending(key: ConversationKey) -> PendingAction | None:
    if _pending_connection_factory is None:
        with _state_lock:
            return _pending_actions.pop(key, None)
    conn = _pending_connection_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT tool_name, arguments_json, actor_member_id, created_at "
            "FROM telegram_pending_actions WHERE chat_id = ? AND telegram_user_id = ?",
            key,
        ).fetchone()
        if row:
            conn.execute(
                "DELETE FROM telegram_pending_actions WHERE chat_id = ? AND telegram_user_id = ?",
                key,
            )
        conn.commit()
        return _pending_from_row(row) if row else None
    finally:
        conn.close()


def is_configured() -> bool:
    return bool(os.getenv("OCABRA_CHAT_URL", "").strip() and mcp_server.MCP_API_KEY)


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OCABRA_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _openai_tools(*, is_admin: bool, actor_member_id: int | None = None) -> list[dict[str, Any]]:
    definitions = copy.deepcopy(mcp_server._tool_definitions())
    allowed = TELEGRAM_TOOLS if is_admin else READ_ONLY_TOOLS
    definitions = [item for item in definitions if item["name"] in allowed]
    if actor_member_id is not None:
        for item in definitions:
            if item["name"] not in {"create_proposal", "create_poll"}:
                continue
            schema = item["inputSchema"]
            schema["properties"].pop("created_by", None)
            schema["required"] = [field for field in schema.get("required", []) if field != "created_by"]
            item["description"] += " The creator is the linked Telegram member."
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


def _known_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop model-invented fields before they enter confirmation state or MCP."""
    definition = next(
        (item for item in mcp_server._tool_definitions() if item["name"] == tool_name), None
    )
    if definition is None:
        return {}
    allowed = definition["inputSchema"].get("properties", {})
    return {key: value for key, value in arguments.items() if key in allowed}


def _conversation_key(chat_id: int, telegram_user_id: int | None) -> ConversationKey:
    # Private chats normally use the same value for both IDs. Including the user
    # ID prevents one member in a group chat from seeing another member's context.
    return int(chat_id), int(telegram_user_id if telegram_user_id is not None else chat_id)


def _confirmation_text(action: PendingAction) -> str:
    display_arguments = _redact_arguments(action.arguments)
    return (
        f"⚠️ Please confirm MCP action {action.tool_name} with /confirm, "
        "or discard it with /cancel.\n"
        f"Arguments: {json.dumps(display_arguments, ensure_ascii=False, sort_keys=True)}"
    )


def _redact_arguments(value: Any) -> Any:
    """Return a display-only copy with conventionally secret fields removed."""
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(marker in str(key).lower() for marker in ("password", "secret", "token", "api_key"))
                else _redact_arguments(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_arguments(item) for item in value]
    return value


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


def _normalized_confirmation_command(text: str) -> str:
    """Normalize Telegram's group-only ``/command@botname`` syntax."""
    normalized = (text or "").strip().lower()
    if normalized.startswith("/") and not any(character.isspace() for character in normalized):
        return normalized.split("@", maxsplit=1)[0]
    return normalized


def answer(
    chat_id: int,
    text: str,
    *,
    telegram_user_id: int | None = None,
    actor_member_id: int | None = None,
    is_admin: bool = False,
    on_proposal_created: Callable[[int, dict[str, Any]], bool] | None = None,
) -> str:
    """Answer natural language and let the model operate ManaVote through MCP tools."""
    url = os.getenv("OCABRA_CHAT_URL", "").strip()
    if not url:
        raise RuntimeError("Natural-language Telegram support is not configured.")

    key = _conversation_key(chat_id, telegram_user_id)
    normalized_text = _normalized_confirmation_command(text)
    if normalized_text in {"/cancel", "cancel"}:
        removed = _pop_pending(key)
        return "✅ Pending action cancelled." if removed else "There is no pending action to cancel."
    if normalized_text in {"/confirm", "confirm"}:
        # Claim before validation/execution so two workers can never run the
        # same mutation and a concurrent replacement cannot pass stale checks.
        pending = _pop_pending(key)
        if not pending:
            return "There is no pending action to confirm."
        confirmation_ttl = float(os.getenv("TELEGRAM_CONFIRM_TTL_SECONDS", "300"))
        if time.time() - pending.created_at > confirmation_ttl:
            return "⌛ That pending action expired. Please request it again."
        if not is_admin:
            return "❌ Only a linked administrator can confirm that action."
        if pending.actor_member_id is not None and pending.actor_member_id != actor_member_id:
            return "❌ The linked member changed. Please request that action again."
        result = _call_mcp(pending.tool_name, pending.arguments, is_admin=True)
        reply = _action_result_text(pending, result)
        if pending.tool_name == "create_proposal" and on_proposal_created is not None:
            try:
                payload = json.loads(result)
            except (TypeError, json.JSONDecodeError):
                payload = {}
            proposal_id = payload.get("proposal_id") if isinstance(payload, dict) else None
            if proposal_id is not None:
                delivered = on_proposal_created(int(proposal_id), dict(pending.arguments))
                if not delivered:
                    reply += "\n⚠️ The proposal was saved, but its group notification could not be sent."
        return reply

    with _state_lock:
        history_snapshot = list(_history[key])
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": os.getenv(
                "TELEGRAM_AGENT_SYSTEM_PROMPT",
                "You are the ManaVote Telegram assistant. Use the supplied tools for ManaVote facts and actions. "
                "For administrators, use list_user_statistics for per-user proposal budget totals and to rank "
                "users by proposed budget, approved budget, or approved budget percentage. "
                "Use list_polls for poll questions and list_user_statistics to compare who created polls or how "
                "many votes their polls received. "
                "Use list_group_purchases for group-purchase costs, quantities, participants, debts, and payments; "
                "administrators can use list_user_statistics to rank group-purchase creators by activity or order value. "
                "Never invent tool results. If a tool says confirmation_required, repeat its confirmation message "
                "and do not claim the action succeeded. Reply concisely in the user's language using plain text "
                "that reads well in Telegram.",
            ),
        },
        *history_snapshot,
        {"role": "user", "content": text},
    ]
    tools = _openai_tools(is_admin=is_admin, actor_member_id=actor_member_id)

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
                arguments = _known_tool_arguments(function["name"], arguments)
                if function["name"] in {"create_proposal", "create_poll"}:
                    if actor_member_id is None:
                        result = json.dumps({"error": "A linked member is required."})
                        messages.append(
                            {"role": "tool", "tool_call_id": tool_call.get("id", ""), "content": result}
                        )
                        continue
                    arguments["created_by"] = actor_member_id
                action = PendingAction(function["name"], arguments, actor_member_id=actor_member_id)
                _put_pending(key, action)
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
    _pop_pending(key)
