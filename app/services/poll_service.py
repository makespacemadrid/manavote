"""Poll lifecycle helpers: closing expired polls and rendering their results."""

import json
from datetime import datetime


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


def build_poll_results_message(conn, poll_id):
    c = conn.cursor()
    c.execute("SELECT id, question, closes_at FROM polls WHERE id = ?", (poll_id,))
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
    lines = [f"📊 *Poll closed: #{poll['id']}*", f"*{poll['question']}*", f"⏰ Closed: {closes_display}", ""]
    if not options:
        lines.append("No valid poll options were found.")
        return "\n".join(lines)

    max_count = max([counts.get(idx, 0) for idx in range(len(options))] + [1])
    for idx, option in enumerate(options):
        count = counts.get(idx, 0)
        pct = (count / total_votes * 100.0) if total_votes else 0.0
        bar_len = int(round((count / max_count) * 12)) if max_count else 0
        bar = "█" * bar_len + "░" * (12 - bar_len)
        lines.append(f"{idx + 1}. {option}")
        lines.append(f"`{bar}` {count} vote(s) ({pct:.1f}%)")
    lines.append("")
    lines.append(f"Total votes: *{total_votes}*")
    return "\n".join(lines)
