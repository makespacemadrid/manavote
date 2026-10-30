"""Validation and persistence for member feedback across REST and MCP."""

VALID_CATEGORIES = {"bug", "suggestion", "other"}
from app.repositories.feedback_repo import FeedbackRepository
from app.db.transactions import write_transaction
from app.services.feedback_notification_service import deliver_resolution
import logging

VALID_STATUSES = {"new", "reviewed", "resolved", "rejected"}
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
    feedback_id = int(cursor.lastrowid)
    FeedbackRepository(conn).add_status_event(feedback_id, 'new')
    conn.commit()
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


def update_feedback_status(conn, *, feedback_id, status, resolved_by, logger=None, public_reason=None):
    if status not in VALID_STATUSES:
        raise FeedbackValidationError("invalid_status", "status must be new, reviewed, resolved, or rejected")
    repo = FeedbackRepository(conn)
    notification_id = None
    with write_transaction(conn):
        item = repo.get(feedback_id)
        if item is None:
            raise FeedbackValidationError('feedback_not_found', 'feedback not found')
        reason = item['public_reason'] if public_reason is None else str(public_reason).strip()
        if len(reason) > MAX_MESSAGE_LENGTH:
            raise FeedbackValidationError('invalid_public_reason', 'Public reason must be at most 4000 characters')
        repo.set_public_reason(feedback_id, reason)
        if item['status'] != status or item['public_reason'] != reason:
            repo.add_status_event(feedback_id, status, reason)
        repo.resolve_status(feedback_id, status, resolved_by)
        if status == 'resolved' and item['status'] != 'resolved':
            notification_id = repo.notify(item)
    if notification_id is not None:
        deliver_resolution(conn, notification_id)
    if logger:
        logger.info("event=feedback_status_changed feedback_id=%s status=%s resolved_by=%s", feedback_id, status, resolved_by)


def manage_feedback(conn, *, action, feedback_id, actor_id, is_admin, message='', category='', note_id=None):
    if not is_admin:
        raise FeedbackValidationError('admin_required', 'Admin access required')
    repo = FeedbackRepository(conn)
    with write_transaction(conn):
        if repo.get(feedback_id) is None:
            raise FeedbackValidationError('feedback_not_found', 'feedback not found')
        message = str(message or '').strip()
        if action in {'add_feedback_note', 'edit_feedback_note', 'edit_feedback'} and (not message or len(message) > 4000):
            raise FeedbackValidationError('invalid_message', 'Feedback text must contain 1 to 4000 characters')
        if action == 'add_feedback_note':
            repo.add_note(feedback_id, actor_id, message)
        elif action == 'edit_feedback_note':
            if not repo.edit_note(feedback_id, note_id, message):
                raise FeedbackValidationError('note_not_found', 'Feedback note not found')
        elif action == 'delete_feedback_note':
            if not repo.delete_note(feedback_id, note_id):
                raise FeedbackValidationError('note_not_found', 'Feedback note not found')
        elif action == 'edit_feedback':
            if category not in VALID_CATEGORIES:
                raise FeedbackValidationError('invalid_category', 'Invalid feedback category')
            repo.edit(feedback_id, message, category)
        elif action == 'delete_feedback':
            repo.delete(feedback_id)
        else:
            raise FeedbackValidationError('invalid_action', 'Invalid feedback action')
    logging.getLogger(__name__).info('event=feedback_admin_action action=%s feedback_id=%s actor_id=%s', action, feedback_id, actor_id)
