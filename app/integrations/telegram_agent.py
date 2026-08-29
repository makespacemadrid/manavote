"""Natural-language Telegram agent backed by an OpenAI-compatible model and MCP.

The Telegram conversation pattern is inspired by Luis Rivera's ocabra_telegram:
https://github.com/luisriverag/ocabra_telegram
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from app import mcp_server
from app.services import mcp_application, mcp_tool_registry

_logger = logging.getLogger(__name__)


def _tools_with_policy(policy):
    return {name for name, assigned in mcp_tool_registry.TELEGRAM_POLICIES.items() if assigned == policy}


READ_ONLY_TOOLS = _tools_with_policy(mcp_tool_registry.TelegramPolicy.MEMBER_READ)
ADMIN_READ_ONLY_TOOLS = _tools_with_policy(mcp_tool_registry.TelegramPolicy.ADMIN_READ)
MUTATING_TOOLS = _tools_with_policy(mcp_tool_registry.TelegramPolicy.CONFIRMED_ADMIN_WRITE)
MEMBER_WRITABLE_TOOLS = _tools_with_policy(mcp_tool_registry.TelegramPolicy.MEMBER_WRITE)
# Tools are deliberately classified here instead of granting administrators every
# MCP tool. In particular, create_member accepts a password and must never be
# exposed to a model-backed Telegram conversation.
TELEGRAM_TOOLS = READ_ONLY_TOOLS | ADMIN_READ_ONLY_TOOLS | MUTATING_TOOLS | MEMBER_WRITABLE_TOOLS
MAX_TOOL_ROUNDS = 4
MAX_HISTORY_MESSAGES = 12
ConversationKey = tuple[int, int]
_history: dict[ConversationKey, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=MAX_HISTORY_MESSAGES))
_history_connection_factory: Callable[[], Any] | None = None
_pending_actions: dict[ConversationKey, "PendingAction"] = {}
_pending_connection_factory: Callable[[], Any] | None = None
_state_lock = threading.RLock()


def configure_history_store(connection_factory: Callable[[], Any] | None) -> None:
    """Use a shared database for conversation history, or memory when factory is ``None``."""
    global _history_connection_factory
    _history_connection_factory = connection_factory


def _get_history(key: ConversationKey) -> list[dict[str, Any]]:
    if _history_connection_factory is None:
        with _state_lock:
            return list(_history[key])
    conn = _history_connection_factory()
    try:
        row = conn.execute(
            "SELECT messages_json FROM telegram_conversation_history "
            "WHERE chat_id = ? AND telegram_user_id = ?",
            key,
        ).fetchone()
        return json.loads(row["messages_json"]) if row else []
    finally:
        conn.close()


def _append_history(key: ConversationKey, messages: list[dict[str, Any]]) -> None:
    """Append messages, keeping only the most recent ``MAX_HISTORY_MESSAGES``."""
    if _history_connection_factory is None:
        with _state_lock:
            _history[key].extend(messages)
        return
    conn = _history_connection_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT messages_json FROM telegram_conversation_history "
            "WHERE chat_id = ? AND telegram_user_id = ?",
            key,
        ).fetchone()
        existing = json.loads(row["messages_json"]) if row else []
        updated = (existing + list(messages))[-MAX_HISTORY_MESSAGES:]
        conn.execute(
            """
            INSERT INTO telegram_conversation_history
                (chat_id, telegram_user_id, messages_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, telegram_user_id) DO UPDATE SET
                messages_json = excluded.messages_json,
                updated_at = excluded.updated_at
            """,
            (*key, json.dumps(updated), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def _clear_history(key: ConversationKey) -> None:
    if _history_connection_factory is None:
        with _state_lock:
            _history.pop(key, None)
        return
    conn = _history_connection_factory()
    try:
        conn.execute(
            "DELETE FROM telegram_conversation_history WHERE chat_id = ? AND telegram_user_id = ?",
            key,
        )
        conn.commit()
    finally:
        conn.close()


@dataclass(frozen=True)
class PendingAction:
    tool_name: str
    arguments: dict[str, Any]
    actor_member_id: int | None = None
    created_at: float = field(default_factory=time.time)
    # Captured at propose time so /confirm can detect the tool registry or the
    # arguments changing underneath a pending action (a process restart picking up a
    # new tool schema, or accidental corruption of the stored row). None for pending
    # actions created before this field existed -- confirm-time checks skip a None.
    schema_fingerprint: str | None = None
    arguments_digest: str | None = None


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
        schema_fingerprint=row["schema_fingerprint"],
        arguments_digest=row["arguments_digest"],
    )


def _get_pending(key: ConversationKey) -> PendingAction | None:
    if _pending_connection_factory is None:
        with _state_lock:
            return _pending_actions.get(key)
    conn = _pending_connection_factory()
    try:
        row = conn.execute(
            "SELECT tool_name, arguments_json, actor_member_id, created_at, "
            "schema_fingerprint, arguments_digest "
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
                (chat_id, telegram_user_id, tool_name, arguments_json, actor_member_id, created_at,
                 schema_fingerprint, arguments_digest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, telegram_user_id) DO UPDATE SET
                tool_name = excluded.tool_name,
                arguments_json = excluded.arguments_json,
                actor_member_id = excluded.actor_member_id,
                created_at = excluded.created_at,
                schema_fingerprint = excluded.schema_fingerprint,
                arguments_digest = excluded.arguments_digest
            """,
            (
                *key,
                action.tool_name,
                json.dumps(action.arguments),
                action.actor_member_id,
                action.created_at,
                action.schema_fingerprint,
                action.arguments_digest,
            ),
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
            "SELECT tool_name, arguments_json, actor_member_id, created_at, "
            "schema_fingerprint, arguments_digest "
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


def _stable_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _schema_fingerprint(tool_name: str) -> str | None:
    """Fingerprint of a tool's current input schema, or None if the tool no longer
    exists. Lets /confirm detect the registry changing underneath a pending action
    (e.g. a process restart picking up a different tool version)."""
    definition = next(
        (item for item in mcp_server.tool_definitions() if item["name"] == tool_name), None
    )
    return _stable_digest(definition["inputSchema"]) if definition is not None else None


def _log_mutation_event(
    event: str,
    reason_code: str,
    *,
    tool_name: str,
    actor_member_id: int | None,
    chat_id: int | None = None,
    telegram_user_id: int | None = None,
    arguments_digest: str | None = None,
) -> None:
    """Reason-coded audit record for one step of a mutation's propose/confirm lifecycle.

    Deliberately a separate event stream from telegram_routes.py's telegram_assistant_job
    records (which cover job-level timing/retries for every assistant request, not just
    mutations): a mutation's audit trail should be findable on its own, the way backup and
    Telegram-link events already are, not mixed into general job telemetry.
    """
    _logger.info(
        "telegram_assistant_mutation %s",
        json.dumps(
            {
                "event": event,
                "reason_code": reason_code,
                "tool_name": tool_name,
                "actor_member_id": actor_member_id,
                "chat_id": chat_id,
                "telegram_user_id": telegram_user_id,
                "arguments_digest": arguments_digest,
            },
            sort_keys=True,
        ),
    )


def is_configured() -> bool:
    return bool(os.getenv("OCABRA_CHAT_URL", "").strip() and mcp_server.MCP_API_KEY)


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OCABRA_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _openai_tools(*, is_admin: bool, actor_member_id: int | None = None) -> list[dict[str, Any]]:
    definitions = mcp_tool_registry.telegram_tool_definitions(
        mcp_server.tool_definitions(), is_admin=is_admin, actor_member_id=actor_member_id
    )
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
    actor = mcp_application.Actor("admin" if is_admin else "member", arguments.get("member_id") or arguments.get("created_by"))
    try:
        response = mcp_application.execute_tool(
            mcp_server.execute_tool_command, tool_name, arguments,
            actor=actor, req_id="telegram-agent",
        )
    except mcp_application.ToolAccessDenied as exc:
        return json.dumps({"error": str(exc)})
    if not response:
        return json.dumps({"error": "MCP returned no response."})
    if "error" in response:
        return json.dumps({"error": response["error"]["message"]})
    content = response.get("result", {}).get("content", [])
    return content[0].get("text", "{}") if content else "{}"


def _known_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop model-invented fields before they enter confirmation state or MCP."""
    definition = next(
        (item for item in mcp_server.tool_definitions() if item["name"] == tool_name), None
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


def _mcp_result_failed(result: str) -> bool:
    try:
        payload = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and bool(payload.get("error"))


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
    on_images: Callable[[list[str]], bool] | None = None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> str:
    """Answer natural language and let the model operate ManaVote through MCP tools."""
    url = os.getenv("OCABRA_CHAT_URL", "").strip()
    if not url:
        raise RuntimeError("Natural-language Telegram support is not configured.")

    key = _conversation_key(chat_id, telegram_user_id)
    normalized_text = _normalized_confirmation_command(text)
    if normalized_text in {"/cancel", "cancel"}:
        removed = _pop_pending(key)
        if removed is None:
            return "There is no pending action to cancel."
        _log_mutation_event(
            "cancelled",
            "user_cancelled",
            tool_name=removed.tool_name,
            actor_member_id=removed.actor_member_id,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            arguments_digest=removed.arguments_digest,
        )
        return "✅ Pending action cancelled."
    if normalized_text in {"/confirm", "confirm"}:
        # Claim before validation/execution so two workers can never run the
        # same mutation and a concurrent replacement cannot pass stale checks.
        pending = _pop_pending(key)
        if not pending:
            return "There is no pending action to confirm."

        def _reject(reason_code: str) -> None:
            _log_mutation_event(
                "rejected",
                reason_code,
                tool_name=pending.tool_name,
                actor_member_id=pending.actor_member_id,
                chat_id=chat_id,
                telegram_user_id=telegram_user_id,
                arguments_digest=pending.arguments_digest,
            )

        confirmation_ttl = float(os.getenv("TELEGRAM_CONFIRM_TTL_SECONDS", "300"))
        if time.time() - pending.created_at > confirmation_ttl:
            _log_mutation_event(
                "expired",
                "confirmation_ttl_exceeded",
                tool_name=pending.tool_name,
                actor_member_id=pending.actor_member_id,
                chat_id=chat_id,
                telegram_user_id=telegram_user_id,
                arguments_digest=pending.arguments_digest,
            )
            return "⌛ That pending action expired. Please request it again."
        if not is_admin:
            _reject("not_admin")
            return "❌ Only a linked administrator can confirm that action."
        if pending.actor_member_id is not None and pending.actor_member_id != actor_member_id:
            _reject("actor_changed")
            return "❌ The linked member changed. Please request that action again."
        if pending.arguments_digest is not None and _stable_digest(pending.arguments) != pending.arguments_digest:
            _reject("arguments_tampered")
            return "❌ That action's arguments changed unexpectedly. Please request it again."
        if pending.schema_fingerprint is not None and _schema_fingerprint(pending.tool_name) != pending.schema_fingerprint:
            _reject("schema_changed")
            return "❌ That action is no longer available in its original form. Please request it again."

        _log_mutation_event(
            "confirmed",
            "ok",
            tool_name=pending.tool_name,
            actor_member_id=pending.actor_member_id,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            arguments_digest=pending.arguments_digest,
        )
        if on_event is not None:
            on_event("tool_call_received", {"tool_name": pending.tool_name})
        result = _call_mcp(pending.tool_name, pending.arguments, is_admin=True)
        failed = _mcp_result_failed(result)
        _log_mutation_event(
            "failed" if failed else "completed",
            "mcp_error" if failed else "ok",
            tool_name=pending.tool_name,
            actor_member_id=pending.actor_member_id,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            arguments_digest=pending.arguments_digest,
        )
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

    history_snapshot = _get_history(key)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": os.getenv(
                "TELEGRAM_AGENT_SYSTEM_PROMPT",
                "You are the ManaVote Telegram assistant. Use the supplied tools for ManaVote facts and actions. "
                "When users ask about proposals, use list_proposals. Include proposal_url and image_url when those "
                "ManaVote links are available. If the user asks for the listed, external, vendor, product, or reference "
                "link, include the separate url field too; label it clearly and never substitute one kind of link for another. "
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
    available_image_urls: set[str] = set()

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        model_started = time.monotonic()
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
        if on_event is not None:
            on_event(
                "model_request_completed",
                {
                    "model_latency_ms": round((time.monotonic() - model_started) * 1000, 2),
                    "model_round": round_number,
                },
            )
        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            reply = (assistant.get("content") or "I couldn't produce a response.").strip()
            selected_images = sorted(url for url in available_image_urls if url in reply)
            if selected_images and on_images is not None:
                on_images(selected_images)
            _append_history(
                key, [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
            )
            return reply

        messages.append(assistant)
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            if on_event is not None:
                on_event(
                    "tool_call_received",
                    {"tool_name": str(function.get("name") or "unknown")},
                )
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except (TypeError, json.JSONDecodeError):
                arguments = {}
            if not isinstance(arguments, dict):
                result = json.dumps({"error": "Tool arguments must be a JSON object."})
            elif function.get("name") in MEMBER_WRITABLE_TOOLS:
                arguments = _known_tool_arguments(function["name"], arguments)
                if actor_member_id is None:
                    result = json.dumps({"error": "A linked member is required."})
                else:
                    arguments["member_id"] = actor_member_id
                    result = _call_mcp(function["name"], arguments, is_admin=is_admin)
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
                action = PendingAction(
                    function["name"],
                    arguments,
                    actor_member_id=actor_member_id,
                    schema_fingerprint=_schema_fingerprint(function["name"]),
                    arguments_digest=_stable_digest(arguments),
                )
                _put_pending(key, action)
                _log_mutation_event(
                    "proposed",
                    "ok",
                    tool_name=action.tool_name,
                    actor_member_id=actor_member_id,
                    chat_id=chat_id,
                    telegram_user_id=telegram_user_id,
                    arguments_digest=action.arguments_digest,
                )
                # Do not rely on the model to reproduce a safety prompt. Return
                # the exact confirmation instructions immediately and avoid an
                # unnecessary second model round.
                return _confirmation_text(action)
            else:
                result = _call_mcp(function.get("name", ""), arguments, is_admin=is_admin)
                if function.get("name") == "list_proposals":
                    try:
                        proposal_payload = json.loads(result)
                    except (TypeError, json.JSONDecodeError):
                        proposal_payload = {}
                    proposals = (
                        proposal_payload.get("proposals", [])
                        if isinstance(proposal_payload, dict)
                        else []
                    )
                    for proposal in proposals:
                        image_url = proposal.get("image_url") if isinstance(proposal, dict) else None
                        if isinstance(image_url, str) and image_url:
                            available_image_urls.add(image_url)
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.get("id", ""), "content": result}
            )

    raise RuntimeError("The assistant exceeded the MCP tool-call limit.")


def reset(chat_id: int, telegram_user_id: int | None = None) -> None:
    key = _conversation_key(chat_id, telegram_user_id)
    _clear_history(key)
    removed = _pop_pending(key)
    if removed is not None:
        _log_mutation_event(
            "cancelled",
            "reset_command",
            tool_name=removed.tool_name,
            actor_member_id=removed.actor_member_id,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            arguments_digest=removed.arguments_digest,
        )
