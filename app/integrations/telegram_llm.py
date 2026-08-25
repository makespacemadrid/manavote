"""Natural-language Telegram agent backed by MCP tools."""

import json
import threading
import time

from app.integrations.llm_client import LLMClientError
from app.integrations.mcp_client import MCPClientError
from app.integrations.telegram_mcp import MAX_TELEGRAM_TEXT, _format_tool_result

DEFAULT_SYSTEM_PROMPT = (
    "You are the ManaVote Telegram assistant. Help members use ManaVote. "
    "Use the provided tools whenever current application data or an action is needed. "
    "Before a tool that creates or changes data, clearly ask the user for confirmation; "
    "never claim an action succeeded unless the tool result confirms it. Keep replies concise."
)
READ_TOOL_PREFIXES = ("list_", "get_", "current_")


def _is_write_tool(tool_name):
    """Treat unknown/future tools as writes unless their name is explicitly read-like."""
    return not tool_name.startswith(READ_TOOL_PREFIXES)


class ConversationStore:
    """Small thread-safe, expiring conversation store keyed by Telegram user."""

    def __init__(self, ttl_seconds=1800, max_messages=10):
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages
        self._items = {}
        self._pending_writes = {}
        self._lock = threading.Lock()

    def get(self, user_id):
        now = time.monotonic()
        with self._lock:
            updated_at, messages = self._items.get(str(user_id), (0, []))
            if now - updated_at > self.ttl_seconds:
                self._items.pop(str(user_id), None)
                return []
            return [dict(message) for message in messages]

    def append_exchange(self, user_id, user_text, assistant_text):
        messages = self.get(user_id)
        messages.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": assistant_text}])
        with self._lock:
            self._items[str(user_id)] = (time.monotonic(), messages[-self.max_messages :])

    def clear(self, user_id):
        with self._lock:
            self._items.pop(str(user_id), None)
            self._pending_writes.pop(str(user_id), None)

    def set_pending_write(self, user_id, tool_name, arguments):
        with self._lock:
            self._pending_writes[str(user_id)] = {
                "name": tool_name,
                "arguments": dict(arguments),
                "created_at": time.monotonic(),
            }

    def get_pending_write(self, user_id):
        with self._lock:
            pending = self._pending_writes.get(str(user_id))
            if not pending or time.monotonic() - pending["created_at"] > self.ttl_seconds:
                self._pending_writes.pop(str(user_id), None)
                return None
            return {"name": pending["name"], "arguments": dict(pending["arguments"])}

    def clear_pending_write(self, user_id):
        with self._lock:
            self._pending_writes.pop(str(user_id), None)


class UpdateDeduplicator:
    """Claim Telegram update IDs once, with bounded expiring memory."""

    def __init__(self, ttl_seconds=600, max_updates=2000):
        self.ttl_seconds = ttl_seconds
        self.max_updates = max_updates
        self._updates = {}
        self._lock = threading.Lock()

    def claim(self, update_id):
        if update_id is None:
            return True
        now = time.monotonic()
        key = str(update_id)
        with self._lock:
            expired = [item for item, seen_at in self._updates.items() if now - seen_at > self.ttl_seconds]
            for item in expired:
                self._updates.pop(item, None)
            if key in self._updates:
                return False
            self._updates[key] = now
            if len(self._updates) > self.max_updates:
                oldest = min(self._updates, key=self._updates.get)
                self._updates.pop(oldest, None)
            return True


def _llm_tools(mcp_tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
    ]


def run_telegram_assistant(
    text, *, llm_client, mcp_client, system_prompt=DEFAULT_SYSTEM_PROMPT,
    history=None, approved_write=None, on_write_blocked=None, max_steps=5,
):
    """Run a bounded LLM/tool loop and return one Telegram-safe response."""
    try:
        tools = _llm_tools(mcp_client.list_tools())
        messages = [{"role": "system", "content": system_prompt}, *(history or []), {"role": "user", "content": text}]
        for _ in range(max_steps):
            message = llm_client.complete(messages, tools)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                response = (message.get("content") or "I couldn't produce a response. Please try again.").strip()
                return response if len(response) <= MAX_TELEGRAM_TEXT else response[: MAX_TELEGRAM_TEXT - 3] + "..."
            messages.append(message)
            for call in tool_calls:
                function = call.get("function") or {}
                try:
                    tool_name = function.get("name", "")
                    arguments = json.loads(function.get("arguments") or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("arguments must be an object")
                    if _is_write_tool(tool_name):
                        requested_write = {"name": tool_name, "arguments": arguments}
                        if requested_write != approved_write:
                            if on_write_blocked:
                                on_write_blocked(tool_name, arguments)
                            raise ValueError("confirmation required before this exact write action; ask the user to confirm")
                    result = _format_tool_result(mcp_client.call_tool(tool_name, arguments))
                except (json.JSONDecodeError, ValueError, MCPClientError) as exc:
                    result = f"Tool error: {exc}"
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
        return "I couldn't finish that request safely. Please try a simpler request."
    except (LLMClientError, MCPClientError) as exc:
        return f"❌ Assistant unavailable: {exc}"
