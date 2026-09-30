"""Poll lifecycle helpers: closing expired polls, rendering their results, and auditing
votes blocked by policy."""

import json
from datetime import datetime

from app.services import voting_mode_service


def close_expired_polls(conn):
    now_iso = datetime.now().isoformat()
    c = conn.cursor()
    c.execute(
        """
        SELECT id
        FROM polls
        WHERE status = 'open'
          AND closes_at IS NOT NULL
          AND closes_at != ''
          AND closes_at <= ?
        """,
        (now_iso,),
    )
    expired_poll_ids = [row["id"] for row in c.fetchall()]
    if not expired_poll_ids:
        return []
    c.execute(
        """
        UPDATE polls
        SET status = 'closed'
        WHERE status = 'open'
          AND closes_at IS NOT NULL
          AND closes_at != ''
          AND closes_at <= ?
        """,
        (now_iso,),
    )
    if c.rowcount:
        conn.commit()
    return expired_poll_ids


def record_poll_vote(conn, poll_id, member_id, option_index, allow_multiple):
    """Record a member's selection for one poll option.

    Single-select polls (`allow_multiple=False`) replace any prior selection with
    this one, matching a radio button. Multi-select polls toggle just this option,
    matching a checkbox -- selecting it if it wasn't already, removing it if it was
    -- leaving the member's other selections on this poll untouched.

    Returns True if `option_index` is selected for this member after the call,
    False if this call just removed it (multi-select only; single-select always
    returns True).
    """
    c = conn.cursor()
    if not allow_multiple:
        c.execute(
            "DELETE FROM poll_votes WHERE poll_id = ? AND member_id = ? AND option_index != ?",
            (poll_id, member_id, option_index),
        )
        c.execute(
            "INSERT OR IGNORE INTO poll_votes (poll_id, member_id, option_index) VALUES (?, ?, ?)",
            (poll_id, member_id, option_index),
        )
        conn.commit()
        return True

    c.execute(
        "SELECT 1 FROM poll_votes WHERE poll_id = ? AND member_id = ? AND option_index = ?",
        (poll_id, member_id, option_index),
    )
    already_selected = c.fetchone() is not None
    if already_selected:
        c.execute(
            "DELETE FROM poll_votes WHERE poll_id = ? AND member_id = ? AND option_index = ?",
            (poll_id, member_id, option_index),
        )
    else:
        c.execute(
            "INSERT INTO poll_votes (poll_id, member_id, option_index) VALUES (?, ?, ?)",
            (poll_id, member_id, option_index),
        )
    conn.commit()
    return not already_selected


def build_poll_announcement_message(question, options, closes_at=None, allow_multiple=False):
    """Announcement text for a newly created poll, shared by every creation path
    (web admin form, REST, MCP) and the admin panel's manual (re)send actions, so the
    wording can't drift between them."""
    lines = [f"*{question}*", "", "📊 New poll", ""]
    for idx, option in enumerate(options, 1):
        lines.append(f"{idx}. {option}")
    lines.append("")
    if closes_at:
        try:
            closes_display = datetime.fromisoformat(closes_at).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            closes_display = closes_at
        lines.append(f"⏰ Closes: {closes_display}")
        lines.append("")
    if allow_multiple:
        lines.append("You may select more than one option. Tap a button below to vote.")
    else:
        lines.append("Tap a button below to vote.")
    return "\n".join(lines)


def build_poll_results_message(conn, poll_id):
    c = conn.cursor()
    c.execute("SELECT id, question, closes_at, allow_multiple FROM polls WHERE id = ?", (poll_id,))
    poll = c.fetchone()
    if not poll:
        return None
    try:
        closes_display = (
            datetime.fromisoformat(poll["closes_at"]).strftime("%Y-%m-%d %H:%M")
            if poll["closes_at"]
            else "n/a"
        )
    except (TypeError, ValueError):
        closes_display = poll["closes_at"] or "n/a"

    c.execute(
        """
        SELECT pv.option_index, COUNT(*) AS vote_count
        FROM poll_votes pv
        WHERE pv.poll_id = ?
        GROUP BY pv.option_index
        ORDER BY pv.option_index ASC
        """,
        (poll_id,),
    )
    counts = {row["option_index"]: row["vote_count"] for row in c.fetchall()}
    c.execute("SELECT options_json FROM polls WHERE id = ?", (poll_id,))
    options_row = c.fetchone()
    try:
        options = json.loads((options_row["options_json"] if options_row else "[]") or "[]")
    except (TypeError, json.JSONDecodeError):
        options = []

    total_votes = sum(counts.values())
    if poll["allow_multiple"]:
        c.execute("SELECT COUNT(DISTINCT member_id) FROM poll_votes WHERE poll_id = ?", (poll_id,))
        percentage_base = c.fetchone()[0]
    else:
        percentage_base = total_votes
    lines = [f"📊 *Poll closed: #{poll['id']}*", f"*{poll['question']}*", f"⏰ Closed: {closes_display}", ""]
    if not options:
        lines.append("No valid poll options were found.")
        return "\n".join(lines)

    max_count = max([counts.get(idx, 0) for idx in range(len(options))] + [1])
    for idx, option in enumerate(options):
        count = counts.get(idx, 0)
        pct = (count / percentage_base * 100.0) if percentage_base else 0.0
        bar_len = int(round((count / max_count) * 12)) if max_count else 0
        bar = "█" * bar_len + "░" * (12 - bar_len)
        lines.append(f"{idx + 1}. {option}")
        lines.append(f"`{bar}` {count} vote(s) ({pct:.1f}%)")
    lines.append("")
    if poll["allow_multiple"]:
        lines.append(f"Total selections: *{total_votes}* from *{percentage_base}* voter(s)")
    else:
        lines.append(f"Total votes: *{total_votes}*")
    return "\n".join(lines)


def log_poll_vote_event(
    logger, get_setting_value, event, source, poll_id=None, member_id=None, reason_code=None
):
    """Reason-coded audit record for a poll vote, mirroring
    proposal_vote_recording_service.log_proposal_vote_event's shape. `poll_id`/
    `member_id` may be None when a vote is blocked before either is resolved (e.g. the
    channel-disabled check runs before any poll/member lookup)."""
    logger.info(
        "event=%s source=%s mode=%s poll_id=%s member_id=%s reason_code=%s",
        event,
        source,
        voting_mode_service.get_poll_vote_mode(get_setting_value),
        poll_id,
        member_id,
        reason_code,
    )
