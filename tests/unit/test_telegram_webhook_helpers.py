from app.integrations.telegram_webhook import (
    callback_vote_response_text,
    classify_message_command,
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


def test_classify_message_command_routes_supported_commands():
    assert classify_message_command("/link a b") == "link"
    assert classify_message_command("/pvote 1 yes") == "proposal_vote"
    assert classify_message_command("/vote 1 2") == "poll_vote"
    assert classify_message_command("hello") == "other"
