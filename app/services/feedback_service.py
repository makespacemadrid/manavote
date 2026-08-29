"""Validation and persistence for member feedback across REST and MCP."""

VALID_CATEGORIES = {"bug", "suggestion", "other"}
VALID_STATUSES = {"new", "reviewed", "resolved"}
VALID_SOURCES = {"web", "telegram", "api"}
MAX_MESSAGE_LENGTH = 4000
MAX_SECTION_LENGTH = 250


class FeedbackValidationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def submit_feedback(conn, *, member_id, source, category, message, section=None, logger=None):
    source = str(source or "").strip().lower()
    category = str(category or "").strip().lower()
    message = str(message or "").strip()
    section = str(section or "").strip() or None
    if source not in VALID_SOURCES:
        raise FeedbackValidationError("invalid_source", "source must be web, telegram, or api")
    if category not in VALID_CATEGORIES:
        raise FeedbackValidationError("invalid_category", "category must be bug, suggestion, or other")
    if not message:
        raise FeedbackValidationError("message_required", "message is required")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise FeedbackValidationError("message_too_long", f"message must be at most {MAX_MESSAGE_LENGTH} characters")
    if section and len(section) > MAX_SECTION_LENGTH:
        raise FeedbackValidationError("section_too_long", f"section must be at most {MAX_SECTION_LENGTH} characters")
    member = conn.execute("SELECT id FROM members WHERE id = ?", (member_id,)).fetchone()
    if not member:
        raise FeedbackValidationError("member_not_found", "member not found")
    cursor = conn.execute(
        "INSERT INTO feedback (member_id, source, category, message, section) VALUES (?, ?, ?, ?, ?)",
        (member_id, source, category, message, section),
    )
    conn.commit()
    feedback_id = int(cursor.lastrowid)
    if logger:
        logger.info("event=feedback_submitted feedback_id=%s member_id=%s source=%s category=%s section=%s", feedback_id, member_id, source, category, section)
    return feedback_id


def list_feedback(conn, *, status=None, category=None, limit=50, offset=0):
    clauses, params = [], []
    if status:
        if status not in VALID_STATUSES:
            raise FeedbackValidationError("invalid_status", "unknown feedback status")
        clauses.append("f.status = ?")
        params.append(status)
    if category:
        if category not in VALID_CATEGORIES:
            raise FeedbackValidationError("invalid_category", "unknown feedback category")
        clauses.append("f.category = ?")
        params.append(category)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT f.*, m.username, r.username AS resolved_by_username
            FROM feedback f JOIN members m ON m.id = f.member_id
            LEFT JOIN members r ON r.id = f.resolved_by
            {where} ORDER BY f.created_at DESC, f.id DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]


def update_feedback_status(conn, *, feedback_id, status, resolved_by, logger=None):
    if status not in VALID_STATUSES:
        raise FeedbackValidationError("invalid_status", "status must be new, reviewed, or resolved")
    cursor = conn.execute(
        """UPDATE feedback SET status = ?, resolved_by = ?,
           resolved_at = CASE WHEN ? = 'resolved' THEN CURRENT_TIMESTAMP ELSE NULL END
           WHERE id = ?""",
        (status, resolved_by, status, feedback_id),
    )
    if not cursor.rowcount:
        raise FeedbackValidationError("feedback_not_found", "feedback not found")
    conn.commit()
    if logger:
        logger.info("event=feedback_status_changed feedback_id=%s status=%s resolved_by=%s", feedback_id, status, resolved_by)
