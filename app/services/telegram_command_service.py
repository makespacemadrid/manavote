"""Deterministic Telegram vote commands: /vote, /pvote, and their callback-button forms.

Each function takes its DB/messaging/settings dependencies as explicit parameters
(`get_db`, `get_setting_value`, `send_telegram_message`, `record_proposal_vote`) rather
than reaching for a module global, so the command-parsing and validation logic here is
testable without a live Telegram client or Flask app context.
"""

import json

from app.services import poll_service, voting_mode_service


def process_telegram_vote_command(
    get_db, get_setting_value, send_telegram_message, telegram_username, command_text, telegram_user_id=None
):
    if not voting_mode_service.is_telegram_poll_voting_enabled(get_setting_value):
        return False, "telegram_disabled"
    command = (command_text or "").strip()
    parts = command.split()
    if len(parts) not in (2, 3):
        return False, "invalid_format"

    command_name = parts[0].lower()
    if not (command_name == "/vote" or command_name.startswith("/vote@")):
        return False, "invalid_format"

    try:
        if len(parts) == 3:
            poll_id = int(parts[1])
            option_number = int(parts[2])
        else:
            option_number = int(parts[1])
            poll_id = None
    except ValueError:
        return False, "invalid_numbers"

    conn = get_db()
    c = conn.cursor()
    try:
        expired_poll_ids = poll_service.close_expired_polls(conn)
        for expired_poll_id in expired_poll_ids:
            message = poll_service.build_poll_results_message(conn, expired_poll_id)
            if message:
                send_telegram_message(message)
        require_linked = voting_mode_service.require_linked_telegram_for_votes(get_setting_value)
        if require_linked:
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        else:
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(username) IN (?, ?) OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        member = c.fetchone()
        if member:
            voter_member_id = member["id"]
        elif telegram_user_id is not None:
            if require_linked:
                return False, "link_required"
            voter_member_id = -abs(int(telegram_user_id))
        else:
            return False, "unknown_member"

        if poll_id is None:
            c.execute("SELECT id, options_json, status FROM polls WHERE status = 'open' ORDER BY id DESC LIMIT 1")
            poll = c.fetchone()
            if not poll:
                return False, "poll_not_found"
            poll_id = poll["id"]
        else:
            c.execute("SELECT id, options_json, status FROM polls WHERE id = ?", (poll_id,))
            poll = c.fetchone()
        if not poll:
            return False, "poll_not_found"
        if poll["status"] != "open":
            return False, "poll_closed"

        try:
            options = json.loads(poll["options_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            options = []
        option_index = option_number - 1
        if option_index < 0 or option_index >= len(options):
            return False, "invalid_option"

        c.execute(
            "INSERT OR REPLACE INTO poll_votes (poll_id, member_id, option_index) VALUES (?, ?, ?)",
            (poll_id, voter_member_id, option_index),
        )
        conn.commit()
        return True, "ok"
    finally:
        conn.close()


def process_telegram_vote_callback(
    get_db,
    get_setting_value,
    send_telegram_message,
    record_proposal_vote,
    telegram_username,
    callback_data,
    telegram_user_id=None,
):
    data = (callback_data or "").strip()
    parts = data.split(":")

    if len(parts) == 3 and parts[0] == "pollvote":
        try:
            option_number = int(parts[2]) + 1
        except ValueError:
            return False, "invalid_numbers"
        return process_telegram_vote_command(
            get_db,
            get_setting_value,
            send_telegram_message,
            telegram_username,
            f"/vote {parts[1]} {option_number}",
            telegram_user_id,
        )

    if len(parts) == 3 and parts[0] == "pvote":
        proposal_id = parts[1]
        vote_token = parts[2]
        return process_telegram_proposal_vote_command(
            get_db,
            get_setting_value,
            record_proposal_vote,
            telegram_username,
            f"/pvote {proposal_id} {vote_token}",
            telegram_user_id,
        )

    return False, "invalid_format"


def process_telegram_proposal_vote_command(
    get_db, get_setting_value, record_proposal_vote, telegram_username, command_text, telegram_user_id=None
):
    command = (command_text or "").strip()
    parts = command.split()
    if len(parts) != 3:
        return False, "invalid_format"

    command_name = parts[0].lower()
    if not (command_name == "/pvote" or command_name.startswith("/pvote@")):
        return False, "invalid_format"

    try:
        proposal_id = int(parts[1])
    except ValueError:
        return False, "invalid_numbers"

    vote_raw = parts[2].strip().lower()
    if vote_raw in {"yes", "y", "in_favor", "favor", "for", "+"}:
        vote = "in_favor"
    elif vote_raw in {"no", "n", "against", "oppose", "-"}:
        vote = "against"
    else:
        return False, "invalid_vote"

    conn = get_db()
    c = conn.cursor()
    try:
        if voting_mode_service.require_linked_telegram_for_votes(get_setting_value):
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        else:
            c.execute(
                "SELECT id FROM members WHERE telegram_user_id = ? OR lower(username) IN (?, ?) OR lower(telegram_username) IN (?, ?)",
                (
                    telegram_user_id,
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                    telegram_username.lower(),
                    f"@{telegram_username.lower()}",
                ),
            )
        member = c.fetchone()
        if not member:
            return False, "link_required" if voting_mode_service.require_linked_telegram_for_votes(get_setting_value) else "unknown_member"

        c.execute("SELECT id, status FROM proposals WHERE id = ?", (proposal_id,))
        proposal = c.fetchone()
        if not proposal:
            return False, "proposal_not_found"
        if proposal["status"] != "active":
            return False, "proposal_closed"

        ok = record_proposal_vote(proposal_id, member["id"], vote, source="telegram")
        if not ok:
            return False, "telegram_disabled"
        return True, "ok"
    finally:
        conn.close()
