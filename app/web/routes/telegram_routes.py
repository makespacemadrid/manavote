import hmac
import json
import sqlite3
import time
from concurrent.futures import CancelledError

import requests
from flask import Blueprint, request

from app.extensions import csrf
from app.integrations import telegram_agent
from app.integrations.telegram_webhook import (
    classify_message_addressing,
    classify_message_command,
    dispatch_callback,
    dispatch_message,
    extract_callback_context,
    extract_message_context,
    is_configured_forum_topic,
)
from app.services.telegram_access_service import get_telegram_principal
from app.web.routes import main_routes as legacy

telegram_bp = Blueprint("telegram", __name__)
TELEGRAM_JOB_FAILURES = (
    requests.RequestException,
    sqlite3.Error,
    RuntimeError,
    KeyError,
    IndexError,
    TypeError,
    ValueError,
)


@telegram_bp.route("/telegram/webhook/<secret>", methods=["POST"], endpoint="webhook")
@csrf.exempt
def telegram_webhook(secret):
    # Local aliases so the body below (relocated from the legacy main_routes module)
    # can reference these names unchanged; each is re-read from the legacy module on
    # every request rather than imported once, so test monkeypatches on main_routes
    # (TELEGRAM_BOT_TOKEN, TelegramClient, _telegram_agent_executor, etc.) and runtime
    # config changes still take effect.
    TELEGRAM_WEBHOOK_SECRET = legacy.TELEGRAM_WEBHOOK_SECRET
    TELEGRAM_BOT_TOKEN = legacy.TELEGRAM_BOT_TOKEN
    TELEGRAM_BOT_USERNAME = legacy.TELEGRAM_BOT_USERNAME
    TELEGRAM_CHAT_ID = legacy.TELEGRAM_CHAT_ID
    TELEGRAM_THREAD_ID = legacy.TELEGRAM_THREAD_ID
    TelegramClient = legacy.TelegramClient
    get_db = legacy.get_db
    get_base_url = legacy.get_base_url
    can_record_proposal_vote = legacy.can_record_proposal_vote
    process_telegram_vote_callback = legacy.process_telegram_vote_callback
    process_telegram_link_command = legacy.process_telegram_link_command
    process_telegram_proposal_vote_command = legacy.process_telegram_proposal_vote_command
    process_telegram_vote_command = legacy.process_telegram_vote_command
    app = legacy.app
    _telegram_update_deduplicator = legacy._telegram_update_deduplicator
    _telegram_agent_executor = legacy._telegram_agent_executor

    if not TELEGRAM_WEBHOOK_SECRET or not hmac.compare_digest(secret, TELEGRAM_WEBHOOK_SECRET):
        return {"ok": False}, 403

    payload = request.get_json(silent=True) or {}
    if not _telegram_update_deduplicator.accept(payload.get("update_id")):
        # Telegram retries webhook deliveries when acknowledgements are delayed.
        # Acknowledge duplicates without repeating votes, model calls, or MCP work.
        return {"ok": True}, 200
    callback_ctx = extract_callback_context(payload)
    if callback_ctx:
        def _load_open_poll_options(poll_id):
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT options_json FROM polls WHERE id = ? AND status = 'open'", (poll_id,))
            poll = c.fetchone()
            conn.close()
            if not poll:
                return None
            try:
                return json.loads(poll["options_json"] or "[]")
            except json.JSONDecodeError:
                return None

        result = dispatch_callback(
            callback_ctx,
            process_vote_callback=process_telegram_vote_callback,
            load_open_poll_options=_load_open_poll_options,
        )
        if TELEGRAM_BOT_TOKEN and result["kind"] == "showvote":
            client = TelegramClient(TELEGRAM_BOT_TOKEN, str(result["chat_id"]), "")
            updated = client.edit_message_with_vote_options(
                str(result["chat_id"]), result["message_id"], result["poll_id"], result["options"]
            )
            callback_text = "✅ Vote options shown" if updated else "❌ Couldn't show vote options"
            TelegramClient(TELEGRAM_BOT_TOKEN, "", "").answer_callback_query(result["callback_query_id"], callback_text)
        elif TELEGRAM_BOT_TOKEN:
            TelegramClient(TELEGRAM_BOT_TOKEN, "", "").answer_callback_query(callback_ctx["callback_query_id"], result["text"])
            if (
                result.get("kind") == "answer_callback"
                and not result.get("success", False)
                and result.get("reason") in {"link_required", "unknown_member"}
                and callback_ctx.get("telegram_user_id")
            ):
                TelegramClient(TELEGRAM_BOT_TOKEN, str(callback_ctx["telegram_user_id"]), "").send_message(result["text"])
        return {"ok": True}, 200

    message_ctx = extract_message_context(payload)
    chat_id = message_ctx["chat_id"]
    if not message_ctx["text"]:
        return {"ok": True}, 200

    # /link contains an application password. Remove the command message as soon
    # as possible (when Telegram permissions allow it), regardless of whether
    # credentials are valid. Linking itself is restricted to private chats below.
    if (
        classify_message_command(message_ctx["text"]) == "link"
        and TELEGRAM_BOT_TOKEN
        and chat_id
        and message_ctx.get("message_id") is not None
    ):
        TelegramClient(TELEGRAM_BOT_TOKEN, str(chat_id), "").delete_message(
            message_ctx["message_id"]
        )

    def _natural_language_reply(ctx, principal=None, on_event=None):
        if not telegram_agent.is_configured():
            return "Natural-language assistance is not configured. Use /help for available commands."
        principal = principal or get_telegram_principal(get_db, ctx["telegram_user_id"])
        if principal is None:
            return "❌ Link your account first with /link <app_username> <app_password>."

        def _notify_created_proposal(proposal_id, arguments):
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT username FROM members WHERE id = ?", (principal.member_id,)
                ).fetchone()
            finally:
                conn.close()
            creator = row["username"].split("@")[0] if row else "Unknown member"
            title = str(arguments.get("title") or "Untitled proposal")
            description = str(arguments.get("description") or "")
            amount = arguments.get("amount")
            proposal_url = str(arguments.get("url") or "")
            message = (
                f"*{title}*\n\n🆕 New proposal\nBy: {creator}\nAmount: €{amount}\n\n"
                f"{description[:200]}{'...' if len(description) > 200 else ''}\n\n"
                f"👉 {proposal_url or 'No link'}\n🔗 {get_base_url().rstrip('/')}/proposal/{proposal_id}"
            )
            client = TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID)
            if can_record_proposal_vote("telegram"):
                return client.send_proposal_vote_message(message, proposal_id)
            return client.send_message(message)

        try:
            return telegram_agent.answer(
                int(ctx["chat_id"]),
                ctx["text"],
                telegram_user_id=principal.telegram_user_id,
                actor_member_id=principal.member_id,
                is_admin=principal.is_admin,
                on_proposal_created=_notify_created_proposal,
                on_images=lambda image_urls: all(client.send_photo(url) for url in image_urls),
                on_event=on_event,
            )
        except (requests.RequestException, RuntimeError, KeyError, IndexError, ValueError) as exc:
            app.logger.warning("Telegram natural-language request failed: %s", exc)
            return "❌ I couldn't contact the ManaVote assistant. Please try again later."

    # Telegram expects webhooks to acknowledge updates quickly. Ocabra may take
    # several seconds (and may perform multiple MCP rounds), so configured
    # natural-language work is completed outside the request thread.
    is_command = classify_message_command(message_ctx["text"]) == "other"
    addressing_reason = classify_message_addressing(message_ctx, TELEGRAM_BOT_USERNAME)
    if addressing_reason == "unaddressed" and is_configured_forum_topic(
        message_ctx, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID
    ):
        # A configured forum topic is a dedicated assistant conversation.
        # Telegram does not attach a mention entity to ordinary messages in
        # that topic, so requiring an @mention makes it appear unresponsive.
        addressing_reason = "forum_topic"
    # Private-chat addressing is never ambiguous (always "private", always routed) --
    # only group/supergroup messages are worth this record, including the
    # "unaddressed" outcome, which is exactly the "why did the bot stay silent here"
    # case this is for.
    if is_command and message_ctx.get("chat_type") not in {None, "", "private"}:
        app.logger.info(
            "telegram_routing_decision reason_code=%s chat_id=%s chat_type=%s addressed=%s",
            addressing_reason,
            chat_id,
            message_ctx.get("chat_type"),
            addressing_reason != "unaddressed",
        )
    if (
        is_command
        and addressing_reason != "unaddressed"
        and telegram_agent.is_configured()
        and TELEGRAM_BOT_TOKEN
        and chat_id
    ):
        # Refresh the allowlist for every update so link/unlink and admin-role
        # changes take effect without a process restart.
        principal = get_telegram_principal(get_db, message_ctx["telegram_user_id"])
        if principal is None:
            # Do not enqueue model work or reveal assistant behavior to senders
            # outside the database-backed allowlist. /help and /link remain
            # available through their deterministic command paths.
            return {"ok": True}, 200

        client = TelegramClient(
            TELEGRAM_BOT_TOKEN,
            str(chat_id),
            str(message_ctx.get("message_thread_id") or ""),
            message_ctx.get("message_id"),
        )
        thinking_message_id = client.send_message_with_id("🤔 Thinking…")
        enqueued_at = time.monotonic()

        def _log_assistant_job(event, reason_code, **details):
            app.logger.info(
                "telegram_assistant_job %s",
                json.dumps(
                    {
                        "event": event,
                        "reason_code": reason_code,
                        "update_id": payload.get("update_id"),
                        "chat_id": chat_id,
                        "actor_member_id": principal.member_id,
                        **details,
                    },
                    sort_keys=True,
                ),
            )

        def _answer_and_send(ctx):
            # This runs on a background thread via the bounded executor, outside the
            # request/response cycle -- nothing else observes an exception raised here
            # (concurrent.futures silently drops it unless something calls
            # future.result()/.exception()), so every exception must be caught and
            # logged here, or a failure becomes a silent, permanent non-reply with the
            # "Thinking..." message either stuck or vanished and no operator signal.
            # _natural_language_reply already turns its own expected failure modes into
            # a user-facing message; this is the last-resort net for everything else
            # (a bug in the tool-calling loop, an exception from on_proposal_created,
            # the outbound Telegram call itself failing).
            started_at = time.monotonic()
            _log_assistant_job(
                "started",
                "worker_started",
                queue_wait_ms=round((started_at - enqueued_at) * 1000, 2),
            )
            outcome = "completed"
            try:
                try:
                    reply = _natural_language_reply(
                        ctx,
                        principal=principal,
                        on_event=lambda event, details: _log_assistant_job(
                            event, event, **details
                        ),
                    )
                except TELEGRAM_JOB_FAILURES:
                    outcome = "reply_generation_failed"
                    app.logger.exception(
                        "Unhandled error generating Telegram assistant reply (chat_id=%s member_id=%s)",
                        ctx.get("chat_id"),
                        principal.member_id,
                    )
                    reply = "❌ Something went wrong answering that. Please try again."
                try:
                    delivered = client.send_long_message(reply)
                    if not delivered:
                        outcome = "reply_delivery_failed"
                        app.logger.warning(
                            "Telegram assistant reply was rejected by Telegram "
                            "(chat_id=%s member_id=%s reason_code=reply_delivery_failed)",
                            ctx.get("chat_id"),
                            principal.member_id,
                        )
                except (requests.RequestException, TypeError, ValueError):
                    outcome = "reply_delivery_failed"
                    app.logger.exception(
                        "Unhandled error delivering Telegram assistant reply (chat_id=%s member_id=%s)",
                        ctx.get("chat_id"),
                        principal.member_id,
                    )
            finally:
                try:
                    deleted = client.delete_message(thinking_message_id)
                    if thinking_message_id is not None and not deleted:
                        if outcome == "completed":
                            outcome = "thinking_cleanup_failed"
                        app.logger.warning(
                            "Telegram assistant thinking message was not deleted "
                            "(chat_id=%s member_id=%s reason_code=thinking_cleanup_failed)",
                            ctx.get("chat_id"),
                            principal.member_id,
                        )
                except (requests.RequestException, TypeError, ValueError):
                    if outcome == "completed":
                        outcome = "thinking_cleanup_failed"
                    app.logger.exception(
                        "Failed to delete Telegram assistant thinking message (chat_id=%s member_id=%s)",
                        ctx.get("chat_id"),
                        principal.member_id,
                    )
            _log_assistant_job(
                "completed",
                outcome,
                job_duration_ms=round((time.monotonic() - started_at) * 1000, 2),
            )

        future = _telegram_agent_executor.submit(_answer_and_send, dict(message_ctx))
        if future is None:
            app.logger.warning("Telegram assistant queue is full; dropping natural-language update")
            _log_assistant_job(
                "rejected",
                "queue_full",
                queue_wait_ms=round((time.monotonic() - enqueued_at) * 1000, 2),
            )
            client.delete_message(thinking_message_id)
            client.send_message("⏳ The assistant is busy right now. Please try again shortly.")
        elif hasattr(future, "add_done_callback"):

            def _observe_worker_result(completed_future):
                try:
                    error = completed_future.exception()
                except CancelledError:
                    _log_assistant_job("completed", "worker_cancelled")
                    return
                if error is not None:
                    app.logger.error(
                        "telegram_assistant_job_unhandled reason_code=unexpected_worker_failure "
                        "update_id=%s chat_id=%s actor_member_id=%s",
                        payload.get("update_id"),
                        chat_id,
                        principal.member_id,
                        exc_info=(type(error), error, error.__traceback__),
                    )

            future.add_done_callback(_observe_worker_result)
        return {"ok": True}, 200

    result = dispatch_message(
        message_ctx,
        process_link_command=process_telegram_link_command,
        process_proposal_vote_command=process_telegram_proposal_vote_command,
        process_poll_vote_command=process_telegram_vote_command,
        process_natural_language=_natural_language_reply,
        process_reset=lambda ctx: telegram_agent.reset(
            int(ctx["chat_id"]), ctx["telegram_user_id"]
        ),
    )
    if TELEGRAM_BOT_TOKEN and chat_id and result["kind"] == "send_message":
        # Commands can arrive inside a forum topic just like natural-language
        # messages.  Keep their deterministic replies in that same topic rather
        # than silently posting them to the supergroup's General topic.
        TelegramClient(
            TELEGRAM_BOT_TOKEN,
            str(chat_id),
            str(message_ctx.get("message_thread_id") or ""),
            message_ctx.get("message_id"),
        ).send_message(result["text"])

    return {"ok": True}, 200
