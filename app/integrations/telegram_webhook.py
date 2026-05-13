"""Telegram webhook payload helpers."""


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
    return {
        "text": text,
        "telegram_username": (from_user.get("username") or "").strip(),
        "telegram_user_id": from_user.get("id"),
        "chat_id": message.get("chat", {}).get("id"),
    }


def classify_message_command(text: str) -> str:
    lowered = (text or "").strip().lower()
    if lowered.startswith("/link"):
        return "link"
    if lowered.startswith("/pvote"):
        return "proposal_vote"
    if lowered.startswith("/vote"):
        return "poll_vote"
    return "other"


def callback_vote_response_text(success, reason):
    if success:
        return "✅ Your vote has been recorded."
    if reason == "telegram_disabled":
        return "❌ Telegram voting is disabled by admin."
    return "❌ Could not record vote."


def proposal_vote_response_text(success, reason):
    if success:
        return "✅ Your proposal vote has been recorded."
    mapping = {
        "telegram_disabled": "❌ Telegram proposal voting is disabled by admin.",
        "unknown_member": "❌ Your Telegram username is not linked to a member account.",
        "link_required": "❌ Your account must be linked first. Use /link <app_username> <app_password> and try again.",
        "proposal_closed": "❌ Proposal is no longer active.",
        "proposal_not_found": "❌ Proposal not found.",
        "invalid_vote": "❌ Invalid vote. Use: yes|no",
        "invalid_format": "❌ Invalid command. Use: /pvote <proposal_id> <yes|no>",
    }
    return mapping.get(reason, "❌ Could not record proposal vote.")


def poll_vote_response_text(success, reason):
    if success:
        return "✅ Your vote has been recorded."
    mapping = {
        "telegram_disabled": "❌ Telegram voting is disabled by admin.",
        "unknown_member": "❌ Your Telegram username is not linked to a member account.",
        "link_required": "❌ Your account must be linked first. Use /link <app_username> <app_password> and try again.",
        "poll_closed": "❌ Poll is closed.",
        "poll_not_found": "❌ Poll not found.",
        "invalid_option": "❌ Invalid option number.",
    }
    return mapping.get(reason, "❌ Invalid command. Use: /vote <option_number>")


def link_response_text(success, reason):
    if success:
        return "✅ Your Telegram account is now linked."
    mapping = {
        "invalid_format": "❌ Usage: /link <app_username> <app_password>",
        "missing_public_username": "❌ Your Telegram account has no public username. In Telegram: Settings → Username, set one, then run /link again.",
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
    }


def dispatch_message(
    message_ctx,
    *,
    process_link_command,
    process_proposal_vote_command,
    process_poll_vote_command,
):
    """Dispatch plain-message commands and return transport-agnostic action."""
    text = message_ctx["text"]
    command_type = classify_message_command(text)
    if command_type == "link":
        if message_ctx["telegram_user_id"] is None:
            return {"kind": "noop"}
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
    return {"kind": "noop"}
