"""Telegram webhook payload helpers."""

import threading
from collections import OrderedDict


class TelegramUpdateDeduplicator:
    """Bounded update-ID store, optionally shared through the application database."""

    def __init__(self, capacity: int = 2048, connection_factory=None):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._connection_factory = connection_factory
        self._seen: OrderedDict[int, None] = OrderedDict()
        self._lock = threading.Lock()

    def accept(self, update_id) -> bool:
        """Return false for a duplicate; payloads without IDs remain processable."""
        if update_id is None:
            return True
        try:
            normalized_id = int(update_id)
        except (TypeError, ValueError):
            return False
        if self._connection_factory is not None:
            return self._accept_shared(normalized_id)
        with self._lock:
            if normalized_id in self._seen:
                return False
            self._seen[normalized_id] = None
            if len(self._seen) > self._capacity:
                self._seen.popitem(last=False)
        return True

    def _accept_shared(self, update_id: int) -> bool:
        """Atomically claim an update ID so retries cannot cross worker boundaries."""
        conn = self._connection_factory()
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO telegram_update_dedup (update_id) VALUES (?)",
                (update_id,),
            )
            accepted = cursor.rowcount == 1
            if accepted:
                conn.execute(
                    """
                    DELETE FROM telegram_update_dedup
                    WHERE update_id IN (
                        SELECT update_id FROM telegram_update_dedup
                        ORDER BY accepted_at DESC, update_id DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (self._capacity,),
                )
            conn.commit()
            return accepted
        finally:
            conn.close()


def extract_callback_context(payload):
    callback_query = payload.get("callback_query") or {}
    if not callback_query:
        return None
    from_user = callback_query.get("from") or {}
    message = callback_query.get("message") or {}
    return {
        "telegram_username": (from_user.get("username") or "").strip(),
        "telegram_user_id": from_user.get("id"),
        "callback_data": callback_query.get("data") or "",
        "callback_query_id": callback_query.get("id") or "",
        "chat_id": message.get("chat", {}).get("id"),
        "message_id": message.get("message_id"),
    }


def extract_message_context(payload):
    message = payload.get("message") or payload.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    reply = message.get("reply_to_message") or {}
    reply_from = reply.get("from") or {}
    # Telegram normally includes the topic ID on the outer message.  Some
    # updates for replies (notably replies to a topic's service/root message)
    # only retain it on ``reply_to_message``.  Preserve that fallback so both
    # assistant routing and outgoing replies stay in the forum topic.
    message_thread_id = message.get("message_thread_id")
    if message_thread_id is None:
        message_thread_id = reply.get("message_thread_id")
    return {
        "text": text,
        "telegram_username": (from_user.get("username") or "").strip(),
        "telegram_user_id": from_user.get("id"),
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type") or "",
        "message_id": message.get("message_id"),
        "message_thread_id": message_thread_id,
        "entities": message.get("entities") or [],
        "reply_to_bot": bool(reply_from.get("is_bot")),
        "reply_to_bot_username": (reply_from.get("username") or "").strip(),
    }


def _telegram_entity_text(text: str, offset, length) -> str:
    """Slice an entity using Telegram's UTF-16 code-unit offsets."""
    try:
        start = int(offset)
        size = int(length)
    except (TypeError, ValueError):
        return ""
    if start < 0 or size < 0:
        return ""
    encoded = text.encode("utf-16-le")
    return encoded[start * 2 : (start + size) * 2].decode("utf-16-le", errors="ignore")


def classify_message_addressing(message_ctx, bot_username: str = "") -> str:
    """Classify why (or whether) this message is addressed to the assistant.

    Returns one of ``private``, ``reply_to_bot``, ``mentioned``, or ``unaddressed``.
    Deliberately does not consider forum-topic routing -- a configured assistant forum
    topic overrides ``unaddressed`` at the call site (see ``is_configured_forum_topic``),
    since that's a routing decision distinct from how this single message is addressed.
    """
    if message_ctx.get("chat_type") in {None, "", "private"}:
        return "private"
    text = message_ctx.get("text") or ""
    normalized_username = bot_username.lstrip("@").casefold()
    expected_mention = f"@{normalized_username}" if normalized_username else ""
    if message_ctx.get("reply_to_bot"):
        reply_username = str(message_ctx.get("reply_to_bot_username") or "").lstrip("@").casefold()
        if not normalized_username or reply_username == normalized_username:
            return "reply_to_bot"

    for entity in message_ctx.get("entities") or []:
        if entity.get("type") not in {"mention", "bot_command"}:
            continue
        value = _telegram_entity_text(text, entity.get("offset"), entity.get("length"))
        # With Telegram privacy mode, an otherwise unidentified mention delivered
        # to the bot is addressed to it. A configured username permits an exact check.
        if not expected_mention or expected_mention in value.casefold():
            return "mentioned"
    return "unaddressed"


def is_natural_language_message(message_ctx, bot_username: str = "") -> bool:
    """Return whether natural chat should handle this private or addressed group message."""
    return classify_message_addressing(message_ctx, bot_username) != "unaddressed"


def is_configured_forum_topic(
    message_ctx, chat_id: str = "", thread_id: str = ""
) -> bool:
    """Return whether a message belongs to the configured assistant forum topic."""
    configured_chat = str(chat_id or "").strip()
    configured_thread = str(thread_id or "").strip()
    if not configured_chat or not configured_thread:
        return False
    return (
        str(message_ctx.get("chat_id") or "").strip() == configured_chat
        and str(message_ctx.get("message_thread_id") or "").strip() == configured_thread
    )


def classify_message_command(text: str) -> str:
    command = (text or "").strip().split(maxsplit=1)[0].lower()
    # Telegram appends @botname to commands sent from group chats.
    command = command.split("@", maxsplit=1)[0]
    if command == "/link":
        return "link"
    if command == "/pvote":
        return "proposal_vote"
    if command == "/vote":
        return "poll_vote"
    if command in {"/start", "/help"}:
        return "help"
    if command == "/reset":
        return "reset"
    return "other"


POLL_VOTE_REASON_MESSAGES = {
    "telegram_disabled": "❌ Telegram voting is disabled by admin.",
    "unknown_member": "❌ Your Telegram username is not linked to a member account.",
    "link_required": "❌ Your account must be linked first. Use /link <app_username> <app_password> and try again.",
    "poll_closed": "❌ Poll is closed.",
    "poll_not_found": "❌ Poll not found.",
    "invalid_option": "❌ Invalid option number.",
}


def callback_vote_response_text(success, reason):
    if success:
        return "✅ Your vote has been recorded."
    return POLL_VOTE_REASON_MESSAGES.get(reason, "❌ Could not record vote.")


def proposal_vote_response_text(success, reason):
    if success:
        return "✅ Your proposal vote has been recorded."
    mapping = {
        "telegram_disabled": "❌ Telegram proposal voting is disabled by admin.",
        "unknown_member": "❌ Your Telegram username is not linked to a member account.",
        "link_required": POLL_VOTE_REASON_MESSAGES["link_required"],
        "proposal_closed": "❌ Proposal is no longer active.",
        "proposal_not_found": "❌ Proposal not found.",
        "invalid_vote": "❌ Invalid vote. Use: yes|no",
        "invalid_format": "❌ Invalid command. Use: /pvote <proposal_id> <yes|no>",
    }
    return mapping.get(reason, "❌ Could not record proposal vote.")


def poll_vote_response_text(success, reason):
    if success:
        return "✅ Your vote has been recorded."
    return POLL_VOTE_REASON_MESSAGES.get(reason, "❌ Invalid command. Use: /vote <option_number>")


def link_response_text(success, reason):
    if success:
        return "✅ Your Telegram account is now linked."
    mapping = {
        "invalid_format": "❌ Usage: /link <app_username> <app_password>",
        "unknown_member": "❌ No member account has that app username.",
        "invalid_credentials": "❌ Invalid username or password.",
        "already_linked": "❌ This Telegram account is already linked to another member.",
    }
    return mapping.get(reason, "❌ Could not link this Telegram account.")


def dispatch_callback(
    callback_ctx,
    *,
    process_vote_callback,
    load_open_poll_options,
):
    """Dispatch callback-query handling into one adapter-friendly payload."""
    callback_data = callback_ctx["callback_data"]
    if callback_data.startswith("showvote:"):
        parts = callback_data.split(":")
        if len(parts) != 2:
            return {"kind": "answer_callback", "text": "❌ Invalid poll"}
        try:
            poll_id = int(parts[1])
        except ValueError:
            return {"kind": "answer_callback", "text": "❌ Invalid poll"}
        options = load_open_poll_options(poll_id)
        if not options:
            return {"kind": "answer_callback", "text": "❌ Poll not found or closed"}
        return {
            "kind": "showvote",
            "poll_id": poll_id,
            "options": options,
            "chat_id": callback_ctx["chat_id"],
            "message_id": callback_ctx["message_id"],
            "callback_query_id": callback_ctx["callback_query_id"],
        }

    success, reason = process_vote_callback(
        callback_ctx["telegram_username"],
        callback_data,
        callback_ctx["telegram_user_id"],
    )
    return {
        "kind": "answer_callback",
        "text": callback_vote_response_text(success, reason),
        "success": success,
        "reason": reason,
    }


def dispatch_message(
    message_ctx,
    *,
    process_link_command,
    process_proposal_vote_command,
    process_poll_vote_command,
    process_natural_language=None,
    process_reset=None,
):
    """Dispatch plain-message commands and return transport-agnostic action."""
    text = message_ctx["text"]
    command_type = classify_message_command(text)
    if command_type == "help":
        return {
            "kind": "send_message",
            "text": (
                "👋 ManaVote bot is running.\n\n"
                "Link your account in a private chat with:\n"
                "/link <app_username> <app_password>\n\n"
                "Once linked, you can ask questions in natural language when the assistant is configured.\n"
                "Use /reset to clear your assistant conversation."
            ),
        }
    if command_type == "reset":
        if process_reset is not None:
            process_reset(message_ctx)
        return {"kind": "send_message", "text": "✅ Assistant conversation cleared."}
    if command_type == "link":
        if message_ctx["telegram_user_id"] is None:
            return {"kind": "noop"}
        if message_ctx.get("chat_type") not in {None, "", "private"}:
            return {
                "kind": "send_message",
                "text": "🔒 For your security, use /link only in a private chat with this bot.",
            }
        success, reason = process_link_command(
            message_ctx["telegram_username"], message_ctx["telegram_user_id"], text
        )
        return {"kind": "send_message", "text": link_response_text(success, reason)}

    if command_type == "proposal_vote":
        success, reason = process_proposal_vote_command(
            message_ctx["telegram_username"], text, message_ctx["telegram_user_id"]
        )
        return {"kind": "send_message", "text": proposal_vote_response_text(success, reason)}

    if command_type == "poll_vote":
        success, reason = process_poll_vote_command(
            message_ctx["telegram_username"], text, message_ctx["telegram_user_id"]
        )
        return {"kind": "send_message", "text": poll_vote_response_text(success, reason)}
    if process_natural_language is not None and text:
        return {"kind": "send_message", "text": process_natural_language(message_ctx)}
    return {"kind": "noop"}
