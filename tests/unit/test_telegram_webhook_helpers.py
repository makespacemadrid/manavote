import sqlite3

from app.integrations.telegram_webhook import (
    callback_vote_response_text,
    classify_message_command,
    dispatch_callback,
    dispatch_message,
    extract_callback_context,
    extract_message_context,
    is_configured_forum_topic,
    is_natural_language_message,
    link_response_text,
    poll_vote_response_text,
    proposal_vote_response_text,
    TelegramUpdateDeduplicator,
)


def test_update_deduplicator_rejects_retries_and_evicts_old_ids():
    deduplicator = TelegramUpdateDeduplicator(capacity=2)
    assert deduplicator.accept(10) is True
    assert deduplicator.accept("10") is False
    assert deduplicator.accept(11) is True
    assert deduplicator.accept(12) is True
    assert deduplicator.accept(10) is True


def test_update_deduplicator_allows_missing_ids_but_rejects_malformed_ids():
    deduplicator = TelegramUpdateDeduplicator()
    assert deduplicator.accept(None) is True
    assert deduplicator.accept(None) is True
    assert deduplicator.accept("invalid") is False


def test_update_deduplicator_shares_claims_across_workers(tmp_path):
    db_path = tmp_path / "updates.db"

    def connect():
        return sqlite3.connect(db_path)

    conn = connect()
    conn.execute(
        "CREATE TABLE telegram_update_dedup ("
        "update_id INTEGER PRIMARY KEY, accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()

    worker_a = TelegramUpdateDeduplicator(capacity=2, connection_factory=connect)
    worker_b = TelegramUpdateDeduplicator(capacity=2, connection_factory=connect)

    assert worker_a.accept(20) is True
    assert worker_b.accept(20) is False
    assert worker_b.accept(21) is True
    assert worker_a.accept(22) is True
    assert worker_b.accept(20) is True


def test_extract_callback_context_parses_callback_payload():
    payload = {
        "callback_query": {
            "id": "abc",
            "data": "pollvote:1:2",
            "from": {"id": 9, "username": "alice"},
            "message": {"message_id": 77, "chat": {"id": 42}},
        }
    }
    ctx = extract_callback_context(payload)
    assert ctx == {
        "telegram_username": "alice",
        "telegram_user_id": 9,
        "callback_data": "pollvote:1:2",
        "callback_query_id": "abc",
        "chat_id": 42,
        "message_id": 77,
    }


def test_extract_message_context_prefers_edited_message_when_message_missing():
    payload = {
        "edited_message": {
            "message_id": 88,
            "text": " /pvote 3 yes ",
            "from": {"id": 12, "username": "bob"},
            "chat": {"id": 999, "type": "private"},
        }
    }
    ctx = extract_message_context(payload)
    assert ctx["text"] == "/pvote 3 yes"
    assert ctx["telegram_username"] == "bob"
    assert ctx["telegram_user_id"] == 12
    assert ctx["chat_id"] == 999
    assert ctx["chat_type"] == "private"
    assert ctx["message_id"] == 88


def test_natural_language_group_message_requires_bot_to_be_addressed():
    ordinary = {
        "text": "hello team",
        "chat_type": "supergroup",
        "entities": [],
        "reply_to_bot": False,
    }
    mentioned = {
        **ordinary,
        "text": "@ManaVoteBot what is our budget?",
        "entities": [{"type": "mention", "offset": 0, "length": 12}],
    }

    assert is_natural_language_message(ordinary, "ManaVoteBot") is False
    assert is_natural_language_message(mentioned, "ManaVoteBot") is True
    assert is_natural_language_message(
        {**ordinary, "reply_to_bot": True, "reply_to_bot_username": "ManaVoteBot"},
        "ManaVoteBot",
    ) is True


def test_natural_language_group_address_uses_utf16_offsets_and_ignores_other_bots():
    text = "👋 @ManaVoteBot budget?"
    # Telegram counts the emoji as two UTF-16 code units.
    mentioned = {
        "text": text,
        "chat_type": "group",
        "entities": [{"type": "mention", "offset": 3, "length": 12}],
        "reply_to_bot": False,
    }
    other_bot_reply = {
        "text": "budget?",
        "chat_type": "group",
        "entities": [],
        "reply_to_bot": True,
        "reply_to_bot_username": "DifferentBot",
    }

    assert is_natural_language_message(mentioned, "ManaVoteBot") is True
    assert is_natural_language_message(other_bot_reply, "ManaVoteBot") is False


def test_extract_message_context_detects_group_reply_and_topic():
    ctx = extract_message_context(
        {
            "message": {
                "message_id": 90,
                "message_thread_id": 7,
                "text": "What about the budget?",
                "from": {"id": 12},
                "chat": {"id": -100, "type": "supergroup"},
                "reply_to_message": {"from": {"id": 99, "is_bot": True}},
            }
        }
    )

    assert ctx["reply_to_bot"] is True
    assert ctx["reply_to_bot_username"] == ""
    assert ctx["message_thread_id"] == 7


def test_extract_message_context_recovers_topic_from_replied_to_message():
    ctx = extract_message_context(
        {
            "message": {
                "message_id": 91,
                "text": "What about the budget?",
                "from": {"id": 12},
                "chat": {"id": -100, "type": "supergroup"},
                "reply_to_message": {
                    "message_id": 7,
                    "message_thread_id": 7,
                    "from": {"id": 99, "is_bot": True},
                },
            }
        }
    )

    assert ctx["message_thread_id"] == 7
    assert ctx["reply_to_bot"] is True


def test_configured_forum_topic_accepts_unmentioned_messages_only_in_exact_topic():
    context = {"chat_id": -100123, "message_thread_id": 42}

    assert is_configured_forum_topic(context, "-100123", "42") is True
    assert is_configured_forum_topic(context, "-100123", "43") is False
    assert is_configured_forum_topic(context, "-100999", "42") is False
    assert is_configured_forum_topic(context, "-100123", "") is False


def test_callback_vote_response_text_handles_disabled_reason():
    assert callback_vote_response_text(False, "telegram_disabled") == "❌ Telegram voting is disabled by admin."
    assert callback_vote_response_text(True, "ok") == "✅ Your vote has been recorded."


def test_callback_vote_response_text_handles_link_required_reason():
    assert "must be linked first" in callback_vote_response_text(False, "link_required")


def test_callback_vote_response_text_uses_generic_fallback_for_unknown_reason():
    assert callback_vote_response_text(False, "unexpected_reason") == "❌ Could not record vote."


def test_proposal_vote_response_text_handles_known_reasons():
    assert proposal_vote_response_text(False, "proposal_not_found") == "❌ Proposal not found."
    assert proposal_vote_response_text(False, "invalid_format") == "❌ Invalid command. Use: /pvote <proposal_id> <yes|no>"
    assert "must be linked first" in proposal_vote_response_text(False, "link_required")


def test_poll_vote_response_text_handles_invalid_option():
    assert poll_vote_response_text(False, "invalid_option") == "❌ Invalid option number."
    assert poll_vote_response_text(True, "ok") == "✅ Your vote has been recorded."
    assert "must be linked first" in poll_vote_response_text(False, "link_required")


def test_link_response_text_handles_known_reasons():
    assert link_response_text(True, "ok") == "✅ Your Telegram account is now linked."
    assert link_response_text(False, "invalid_credentials") == "❌ Invalid username or password."


def test_classify_message_command_routes_supported_commands():
    assert classify_message_command("/link a b") == "link"
    assert classify_message_command("/pvote 1 yes") == "proposal_vote"
    assert classify_message_command("/vote 1 2") == "poll_vote"
    assert classify_message_command("hello") == "other"
    assert classify_message_command("/reset") == "reset"


def test_classify_message_command_accepts_group_mentions_but_not_prefixes():
    assert classify_message_command("/link@ManaVoteBot user pass") == "link"
    assert classify_message_command("/help@ManaVoteBot") == "help"
    assert classify_message_command("/linked user pass") == "other"


def test_dispatch_message_answers_start_as_bot_health_check():
    result = dispatch_message(
        {"text": "/start", "telegram_username": "alice", "telegram_user_id": 5, "chat_id": 1},
        process_link_command=lambda *_: (False, "unused"),
        process_proposal_vote_command=lambda *_: (False, "unused"),
        process_poll_vote_command=lambda *_: (False, "unused"),
    )

    assert result["kind"] == "send_message"
    assert "ManaVote bot is running" in result["text"]
    assert "/link <app_username> <app_password>" in result["text"]


def test_dispatch_message_resets_natural_language_conversation():
    reset_contexts = []
    context = {"text": "/reset", "telegram_username": "alice", "telegram_user_id": 5, "chat_id": 1}
    result = dispatch_message(
        context,
        process_link_command=lambda *_: (False, "unused"),
        process_proposal_vote_command=lambda *_: (False, "unused"),
        process_poll_vote_command=lambda *_: (False, "unused"),
        process_reset=reset_contexts.append,
    )
    assert result == {"kind": "send_message", "text": "✅ Assistant conversation cleared."}
    assert reset_contexts == [context]


def test_dispatch_message_rejects_link_credentials_in_group_chat():
    link_calls = []
    result = dispatch_message(
        {
            "text": "/link alice secret",
            "telegram_username": "alice",
            "telegram_user_id": 5,
            "chat_id": -100,
            "chat_type": "supergroup",
            "message_id": 10,
        },
        process_link_command=lambda *args: link_calls.append(args) or (True, "ok"),
        process_proposal_vote_command=lambda *_: (False, "unused"),
        process_poll_vote_command=lambda *_: (False, "unused"),
    )
    assert "private chat" in result["text"]
    assert link_calls == []


def test_callback_and_poll_vote_share_reason_mappings():
    assert callback_vote_response_text(False, "unknown_member") == poll_vote_response_text(False, "unknown_member")
    assert callback_vote_response_text(False, "link_required") == poll_vote_response_text(False, "link_required")


def test_proposal_and_poll_vote_share_link_required_text():
    assert proposal_vote_response_text(False, "link_required") == poll_vote_response_text(False, "link_required")


def test_dispatch_callback_routes_showvote_with_options():
    ctx = {
        "telegram_username": "alice",
        "telegram_user_id": 5,
        "callback_data": "showvote:7",
        "callback_query_id": "cb-1",
        "chat_id": 100,
        "message_id": 10,
    }
    result = dispatch_callback(
        ctx,
        process_vote_callback=lambda *_: (False, "unused"),
        load_open_poll_options=lambda poll_id: ["yes", "no"] if poll_id == 7 else None,
    )
    assert result["kind"] == "showvote"
    assert result["poll_id"] == 7
    assert result["options"] == ["yes", "no"]


def test_dispatch_callback_falls_back_to_vote_callback_response():
    ctx = {
        "telegram_username": "alice",
        "telegram_user_id": 5,
        "callback_data": "pollvote:3:1",
        "callback_query_id": "cb-2",
        "chat_id": 100,
        "message_id": 10,
    }
    result = dispatch_callback(
        ctx,
        process_vote_callback=lambda *_: (False, "telegram_disabled"),
        load_open_poll_options=lambda *_: None,
    )
    assert result == {
        "kind": "answer_callback",
        "text": "❌ Telegram voting is disabled by admin.",
        "success": False,
        "reason": "telegram_disabled",
    }


def test_dispatch_message_routes_link_and_noop():
    message_ctx = {"text": "/link user pass", "telegram_username": "alice", "telegram_user_id": 5, "chat_id": 1}
    result = dispatch_message(
        message_ctx,
        process_link_command=lambda *_: (True, "ok"),
        process_proposal_vote_command=lambda *_: (False, "unused"),
        process_poll_vote_command=lambda *_: (False, "unused"),
    )
    assert result == {"kind": "send_message", "text": "✅ Your Telegram account is now linked."}

    noop_result = dispatch_message(
        {"text": "hello", "telegram_username": "alice", "telegram_user_id": 5, "chat_id": 1},
        process_link_command=lambda *_: (True, "ok"),
        process_proposal_vote_command=lambda *_: (True, "ok"),
        process_poll_vote_command=lambda *_: (True, "ok"),
    )
    assert noop_result == {"kind": "noop"}


def test_dispatch_message_does_not_call_poll_handler_for_non_command_text():
    called = {"poll": 0}

    def _poll_handler(*_args):
        called["poll"] += 1
        return True, "ok"

    result = dispatch_message(
        {"text": "just chatting", "telegram_username": "alice", "telegram_user_id": 5, "chat_id": 1},
        process_link_command=lambda *_: (True, "ok"),
        process_proposal_vote_command=lambda *_: (True, "ok"),
        process_poll_vote_command=_poll_handler,
    )
    assert result == {"kind": "noop"}
    assert called["poll"] == 0


def test_dispatch_message_returns_link_required_text_for_poll_vote_command():
    result = dispatch_message(
        {"text": "/vote 2 1", "telegram_username": "alice", "telegram_user_id": 5, "chat_id": 1},
        process_link_command=lambda *_: (True, "ok"),
        process_proposal_vote_command=lambda *_: (True, "ok"),
        process_poll_vote_command=lambda *_: (False, "link_required"),
    )
    assert result["kind"] == "send_message"
    assert "must be linked first" in result["text"]
