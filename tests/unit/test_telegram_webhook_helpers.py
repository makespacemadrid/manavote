from app.integrations.telegram_webhook import (
    callback_vote_response_text,
    classify_message_command,
    dispatch_callback,
    dispatch_message,
    extract_callback_context,
    extract_message_context,
    link_response_text,
    poll_vote_response_text,
    proposal_vote_response_text,
)


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
            "text": " /pvote 3 yes ",
            "from": {"id": 12, "username": "bob"},
            "chat": {"id": 999},
        }
    }
    ctx = extract_message_context(payload)
    assert ctx["text"] == "/pvote 3 yes"
    assert ctx["telegram_username"] == "bob"
    assert ctx["telegram_user_id"] == 12
    assert ctx["chat_id"] == 999


def test_callback_vote_response_text_handles_disabled_reason():
    assert callback_vote_response_text(False, "telegram_disabled") == "❌ Telegram voting is disabled by admin."
    assert callback_vote_response_text(True, "ok") == "✅ Your vote has been recorded."


def test_proposal_vote_response_text_handles_known_reasons():
    assert proposal_vote_response_text(False, "proposal_not_found") == "❌ Proposal not found."
    assert proposal_vote_response_text(False, "invalid_format") == "❌ Invalid command. Use: /pvote <proposal_id> <yes|no>"


def test_poll_vote_response_text_handles_invalid_option():
    assert poll_vote_response_text(False, "invalid_option") == "❌ Invalid option number."
    assert poll_vote_response_text(True, "ok") == "✅ Your vote has been recorded."


def test_link_response_text_handles_known_reasons():
    assert link_response_text(True, "ok") == "✅ Your Telegram account is now linked."
    assert link_response_text(False, "invalid_credentials") == "❌ Invalid username or password."
    assert "set one, then run /link again" in link_response_text(False, "missing_public_username")


def test_classify_message_command_routes_supported_commands():
    assert classify_message_command("/link a b") == "link"
    assert classify_message_command("/pvote 1 yes") == "proposal_vote"
    assert classify_message_command("/vote 1 2") == "poll_vote"
    assert classify_message_command("hello") == "other"


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
    assert result == {"kind": "answer_callback", "text": "❌ Telegram voting is disabled by admin."}


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
