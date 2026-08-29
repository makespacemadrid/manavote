"""Lightweight MCP server for ManaVote admin data (JSON-RPC)."""

from __future__ import annotations

import base64
import binascii
import hmac
import http.server
import json
import logging
import os
import secrets
import socketserver
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from werkzeug.security import generate_password_hash

from app.domain.enums import ProposalStatus
from app.repositories.poll_repo import PollRepository
from app.repositories.proposal_repo import ProposalRepository
from app.services import feedback_service, pagination_service, voting_settings_service
from app.services import mcp_application
from app.services.creation_validation_service import normalize_poll_options
from app.services.telegram_link_diagnostics import LINKED_CONDITION_SQL, link_state_case_sql
from app.services.user_statistics import user_statistics_query, user_statistics_rows, user_statistics_total_query
from app.services.voting_settings_service import VALID_VOTE_MODES

DB_PATH = os.getenv("APP_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db"))
UPLOAD_FOLDER = os.getenv(
    "UPLOAD_FOLDER", os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
)
MCP_API_KEY = os.getenv("MCP_API_KEY", "")
MAX_PROPOSAL_IMAGE_BYTES = 10 * 1024 * 1024
VALID_PROPOSAL_STATUSES = {status.value for status in ProposalStatus}
VALID_GROUP_PURCHASE_STATUSES = {"open", "ordered", "received"}
TOOL_ALIASES = {"crreate_proposal": "create_proposal"}
MCP_APPLICATION_FAILURES = (sqlite3.Error, OSError, KeyError, TypeError, ValueError)
logger = logging.getLogger(__name__)


def _db_rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _db_execute(query: str, params: tuple[Any, ...] = ()) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def _create_proposal_record(
    title: str,
    description: str,
    amount_val: float,
    url: str,
    created_by_val: int,
    basic_supplies: int,
    image_filename: str | None = None,
) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        return int(
            ProposalRepository(conn).create(
                title, description, amount_val, url, created_by_val, basic_supplies, image_filename
            )
            or 0
        )
    finally:
        conn.close()


def _save_proposal_image(value: Any) -> str:
    """Decode an MCP-supplied PNG/JPEG and return its local upload filename."""
    mime_type = ""
    encoded: Any = value
    if isinstance(value, dict):
        encoded = value.get("data")
        mime_type = str(value.get("mime_type") or value.get("mimeType") or "").lower()
    if not isinstance(encoded, str) or not encoded.strip():
        raise ValueError("image must contain base64-encoded PNG or JPEG data")

    encoded = encoded.strip()
    if encoded.startswith("data:"):
        header, separator, encoded = encoded.partition(",")
        if not separator or ";base64" not in header.lower():
            raise ValueError("image data URL must be base64 encoded")
        mime_type = header[5:].split(";", 1)[0].lower()
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image contains invalid base64 data") from exc
    if not image_bytes or len(image_bytes) > MAX_PROPOSAL_IMAGE_BYTES:
        raise ValueError("image must be between 1 byte and 10 MiB")

    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        extension, detected_mime = "png", "image/png"
    elif image_bytes.startswith(b"\xff\xd8\xff"):
        extension, detected_mime = "jpg", "image/jpeg"
    else:
        raise ValueError("image must be a PNG or JPEG")
    if mime_type and mime_type not in {detected_mime, "image/jpg" if extension == "jpg" else detected_mime}:
        raise ValueError("image MIME type does not match its contents")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = f"{secrets.token_hex(8)}.{extension}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    with open(path, "xb") as image_file:
        image_file.write(image_bytes)
    return filename


def _remove_uploaded_image(filename: str | None) -> None:
    if not filename:
        return
    try:
        os.remove(os.path.join(UPLOAD_FOLDER, filename))
    except FileNotFoundError:
        pass


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _tool_text(req_id: Any, payload: Any) -> dict[str, Any]:
    return _result(req_id, {"content": [{"type": "text", "text": json.dumps(payload)}]})


def _as_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _read_voting_settings() -> dict[str, Any]:
    rows = _db_rows("SELECT key, value FROM settings WHERE key IN ('poll_vote_mode', 'proposal_vote_mode', 'telegram_require_linked_vote')")
    kv = {r["key"]: r["value"] for r in rows}
    return {
        "poll_vote_mode": kv.get("poll_vote_mode", "both"),
        "proposal_vote_mode": kv.get("proposal_vote_mode", "both"),
        "telegram_require_linked_vote": str(kv.get("telegram_require_linked_vote", "false")).lower() == "true",
    }


def _authorized(req: dict[str, Any], method: str, headers: dict[str, str] | None = None) -> bool:
    if method == "notifications/initialized":
        return True
    headers = headers or {}
    header_key = headers.get("x-api-key", "")
    if not header_key:
        auth_header = headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            header_key = auth_header[7:]
    params = req.get("params")
    body_key = params.get("api_key") if isinstance(params, dict) else None
    provided = header_key or (body_key if isinstance(body_key, str) else "")
    return bool(MCP_API_KEY) and hmac.compare_digest(provided, MCP_API_KEY)



def _pagination_properties(maximum: int) -> dict[str, Any]:
    return {
        "limit": {"type": "integer", "minimum": 1, "maximum": maximum},
        "offset": {"type": "integer", "minimum": 0},
    }


def _paginate(
    req_id: Any, arguments: dict[str, Any], default_limit: int, max_limit: int
) -> tuple[int | None, int | None, dict[str, Any] | None]:
    """Shared with the REST transport via app.services.pagination_service so limit/offset
    validation can't silently drift between the two -- see that module's docstring."""
    limit, offset, reason_code = pagination_service.parse_limit_offset(
        arguments.get("limit"), arguments.get("offset"), default_limit, max_limit
    )
    if reason_code is None:
        return limit, offset, None
    message = pagination_service.REASON_MESSAGES[reason_code].format(max_limit=max_limit)
    return None, None, _error(req_id, -32602, f"Invalid params: {message}")


def tool_definitions() -> list[dict[str, Any]]:
    """Return the MCP discovery contract in a reviewable structure."""

    return [
        {
            "name": "list_proposals",
            "description": (
                "List latest proposals, optionally filtered by status and age. Each proposal includes "
                "its creation and lifecycle dates (processed, over-budget, and purchased), plus comments "
                "and comment authors, its basic-supplies flag, and votes with voter, choice, and date "
                "alongside in-favor/against totals. Returns the original reference URL plus public "
                "proposal_url and image_url links when configured."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": sorted(VALID_PROPOSAL_STATUSES)},
                    "age": {
                        "type": "string",
                        "enum": ["recent", "old"],
                        "description": "Active proposals newer than 30 days (recent) or at least 30 days old (old).",
                    },
                    "proposal_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Return the proposal with this exact ID.",
                    },
                    "username": {"type": "string", "minLength": 1, "description": "Exact creator username."},
                    **_pagination_properties(200),
                },
            },
        },
        {
            "name": "list_polls",
            "description": (
                "List polls with their creator, options, and vote totals. Filter by poll status or exact creator username."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "closed"]},
                    "username": {"type": "string", "minLength": 1, "description": "Exact creator username."},
                    **_pagination_properties(200),
                },
            },
        },
        {
            "name": "list_user_statistics",
            "description": (
                "List per-user proposal, poll, vote, comment, and proposal-budget statistics. "
                "Budget fields include the total proposed amount, approved amount, and approved percentage; "
                "use username for one user or sort_by to rank users."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "minLength": 1},
                    "include_email": {
                        "type": "boolean",
                        "description": "Include member email addresses. Defaults to false.",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": [
                            "participation",
                            "proposed_budget",
                            "approved_budget",
                            "approved_budget_percentage",
                            "poll_count",
                            "created_poll_vote_count",
                            "average_votes_per_created_poll",
                            "group_purchase_count",
                            "created_group_purchase_order_value",
                            "created_group_purchase_participant_count",
                            "username",
                        ],
                    },
                    "sort_direction": {"type": "string", "enum": ["asc", "desc"]},
                    **_pagination_properties(500),
                },
            },
        },
        {
            "name": "list_group_purchases",
            "description": (
                "List group purchases with creators, priced components, shared costs, participants, amounts owed, and payment state. "
                "Filter by status or exact creator username."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": sorted(VALID_GROUP_PURCHASE_STATUSES)},
                    "username": {"type": "string", "minLength": 1, "description": "Exact creator username."},
                    **_pagination_properties(200),
                },
            },
        },
        {
            "name": "current_budget",
            "description": "Get configured current budget setting.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_member_telegram_links",
            "description": "List members and Telegram link information.",
            "inputSchema": {
                "type": "object",
                "properties": {"include_unlinked": {"type": "boolean"}, **_pagination_properties(500)},
            },
        },
        {
            "name": "get_voting_settings",
            "description": "Get current voting settings.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "update_voting_settings",
            "description": "Update voting settings.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "poll_vote_mode": {"type": "string", "enum": sorted(VALID_VOTE_MODES)},
                    "proposal_vote_mode": {"type": "string", "enum": sorted(VALID_VOTE_MODES)},
                    "telegram_require_linked_vote": {"type": "boolean"},
                },
            },
        },
        {
            "name": "create_feedback",
            "description": "Submit a bug report, suggestion, or other feedback for the linked member.",
            "inputSchema": {
                "type": "object",
                "required": ["category", "message", "member_id"],
                "properties": {
                    "category": {"type": "string", "enum": sorted(feedback_service.VALID_CATEGORIES)},
                    "message": {"type": "string", "minLength": 1, "maxLength": feedback_service.MAX_MESSAGE_LENGTH},
                    "member_id": {"type": "integer", "minimum": 1},
                },
            },
        },
        {
            "name": "create_member",
            "description": "Create a member (admin-only action).",
            "inputSchema": {
                "type": "object",
                "required": ["username", "password"],
                "properties": {
                    "username": {"type": "string", "minLength": 1},
                    "password": {"type": "string", "minLength": 1},
                    "is_admin": {"type": "boolean"},
                },
            },
        },
        {
            "name": "create_proposal",
            "description": "Create a proposal, including its link and optional PNG/JPEG image (admin-only action).",
            "inputSchema": {
                "type": "object",
                "required": ["title", "amount", "created_by"],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "description": {"type": "string"},
                    "amount": {"type": "number", "exclusiveMinimum": 0},
                    "url": {"type": "string"},
                    "image": {
                        "description": (
                            "PNG/JPEG as a base64 data URL, raw base64 string, or an object with data and mime_type."
                        ),
                        "oneOf": [
                            {"type": "string", "minLength": 1},
                            {
                                "type": "object",
                                "required": ["data"],
                                "properties": {
                                    "data": {"type": "string", "minLength": 1},
                                    "mime_type": {"type": "string", "enum": ["image/png", "image/jpeg"]},
                                },
                            },
                        ],
                    },
                    "basic_supplies": {"type": "boolean"},
                    "created_by": {"type": "integer", "minimum": 1},
                },
            },
        },
        {
            "name": "create_poll",
            "description": "Create a poll (admin-only action).",
            "inputSchema": {
                "type": "object",
                "required": ["question", "options", "created_by"],
                "properties": {
                    "question": {"type": "string", "minLength": 5, "maxLength": 200},
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "created_by": {"type": "integer", "minimum": 1},
                },
            },
        },
    ]

def execute_tool_command(tool_name: str, arguments: dict[str, Any], *, req_id: Any = 1) -> dict[str, Any]:
    """Execute a validated MCP tool without transport authentication.

    JSON-RPC authenticates before calling this boundary; in-process adapters apply
    their actor policy before invoking it directly.
    """
    if not isinstance(tool_name, str):
        return _error(req_id, -32602, "Invalid params: tool name is required")
    if not isinstance(arguments, dict):
        return _error(req_id, -32602, "Invalid params: arguments must be an object")
    normalized_name = TOOL_ALIASES.get(tool_name, tool_name)
    alias_warning = None
    if normalized_name != tool_name:
        alias_warning = f"Deprecated tool alias '{tool_name}' used; please use '{normalized_name}'"

    if normalized_name == "list_proposals":
        status = str(arguments.get("status") or "").strip().lower()
        age = str(arguments.get("age") or "").strip().lower()
        proposal_id = arguments.get("proposal_id")
        if proposal_id is not None and (
            isinstance(proposal_id, bool)
            or not isinstance(proposal_id, int)
            or proposal_id < 1
        ):
            return _error(
                req_id, -32602, "Invalid params: proposal_id must be a positive integer"
            )
        username = str(arguments.get("username") or "").strip()
        if "username" in arguments and not username:
            return _error(req_id, -32602, "Invalid params: username must not be empty")
        if status and status not in VALID_PROPOSAL_STATUSES:
            return _error(req_id, -32602, "Invalid params: unknown status filter")
        if age not in {"", "recent", "old"}:
            return _error(req_id, -32602, "Invalid params: age must be recent or old")
        if age and status and status != "active":
            return _error(req_id, -32602, "Invalid params: age can only be combined with status=active")
        limit, offset, pagination_error = _paginate(req_id, arguments, default_limit=20, max_limit=200)
        if pagination_error:
            return pagination_error
        query = (
            "SELECT p.id,p.title,p.description,p.amount,p.url,p.image_filename,p.status,"
            "p.created_at,p.processed_at,p.over_budget_at,p.purchased_at,p.basic_supplies,"
            "p.created_by,m.username, "
            "(SELECT COUNT(*) FROM votes v WHERE v.proposal_id = p.id AND v.vote = 'in_favor') AS yes_votes, "
            "(SELECT COUNT(*) FROM votes v WHERE v.proposal_id = p.id AND v.vote = 'against') AS no_votes, "
            "COALESCE((SELECT json_group_array(json_object("
            "'id', ordered_votes.id, 'member_id', ordered_votes.member_id, "
            "'username', ordered_votes.username, 'vote', ordered_votes.vote, "
            "'created_at', ordered_votes.created_at)) FROM ("
            "SELECT v.id,v.member_id,vm.username,v.vote,v.created_at FROM votes v "
            "JOIN members vm ON vm.id = v.member_id WHERE v.proposal_id = p.id "
            "ORDER BY v.created_at ASC,v.id ASC) AS ordered_votes), '[]') AS votes_json, "
            "COALESCE((SELECT json_group_array(json_object("
            "'id', ordered_comments.id, 'member_id', ordered_comments.member_id, "
            "'username', ordered_comments.username, 'content', ordered_comments.content, "
            "'created_at', ordered_comments.created_at)) FROM ("
            "SELECT c.id,c.member_id,cm.username,c.content,c.created_at FROM comments c "
            "JOIN members cm ON cm.id = c.member_id WHERE c.proposal_id = p.id "
            "ORDER BY c.created_at ASC,c.id ASC) AS ordered_comments), '[]') AS comments_json, "
            "(SELECT value FROM settings WHERE key = 'url' LIMIT 1) AS public_base_url "
            "FROM proposals p JOIN members m ON m.id = p.created_by"
        )
        conditions: list[str] = []
        query_params: list[Any] = []
        if proposal_id is not None:
            conditions.append("p.id = ?")
            query_params.append(proposal_id)
        if status:
            conditions.append("p.status = ?")
            query_params.append(status)
        if age:
            if not status:
                conditions.append("p.status = 'active'")
            comparator = ">" if age == "recent" else "<="
            conditions.append(f"datetime(p.created_at) {comparator} datetime(?)")
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).replace(tzinfo=None).isoformat(sep=" ")
            query_params.append(cutoff)
        if username:
            conditions.append("m.username = ? COLLATE NOCASE")
            query_params.append(username)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
        rows = _db_rows(query, tuple(query_params) + (limit, offset))
        for row in rows:
            votes_json = row.pop("votes_json", "[]")
            try:
                row["votes"] = json.loads(votes_json) if votes_json else []
            except (TypeError, json.JSONDecodeError):
                row["votes"] = []
            comments_json = row.pop("comments_json", "[]")
            try:
                row["comments"] = json.loads(comments_json) if comments_json else []
            except (TypeError, json.JSONDecodeError):
                row["comments"] = []
            base_url = str(row.pop("public_base_url", "") or "").rstrip("/")
            row["proposal_url"] = f"{base_url}/proposal/{row['id']}" if base_url else None
            image_filename = row.get("image_filename")
            row["image_url"] = (
                f"{base_url}/static/uploads/{quote(str(image_filename), safe='')}"
                if base_url and image_filename
                else None
            )
        return _tool_text(req_id, {"count": len(rows), "limit": limit, "offset": offset, "proposals": rows})

    if normalized_name == "list_polls":
        status = str(arguments.get("status") or "").strip().lower()
        username = str(arguments.get("username") or "").strip()
        if status not in {"", "open", "closed"}:
            return _error(req_id, -32602, "Invalid params: poll status must be open or closed")
        if "username" in arguments and not username:
            return _error(req_id, -32602, "Invalid params: username must not be empty")
        limit, offset, pagination_error = _paginate(req_id, arguments, default_limit=20, max_limit=200)
        if pagination_error:
            return pagination_error
        conditions: list[str] = []
        query_params: list[Any] = []
        if status:
            conditions.append("p.status = ?")
            query_params.append(status)
        if username:
            conditions.append("m.username = ? COLLATE NOCASE")
            query_params.append(username)
        query = """
            SELECT p.id,p.question,p.options_json,p.status,p.created_at,p.closes_at,
                   p.created_by,m.username,COUNT(pv.id) AS total_votes
            FROM polls p
            JOIN members m ON m.id = p.created_by
            LEFT JOIN poll_votes pv ON pv.poll_id = p.id
        """
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " GROUP BY p.id ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
        rows = _db_rows(query, tuple(query_params) + (limit, offset))
        vote_counts: dict[int, dict[int, int]] = {}
        poll_ids = [int(row["id"]) for row in rows]
        if poll_ids:
            placeholders = ",".join("?" for _ in poll_ids)
            count_rows = _db_rows(
                f"SELECT poll_id,option_index,COUNT(*) AS votes FROM poll_votes "
                f"WHERE poll_id IN ({placeholders}) GROUP BY poll_id,option_index",
                tuple(poll_ids),
            )
            for count_row in count_rows:
                vote_counts.setdefault(int(count_row["poll_id"]), {})[
                    int(count_row["option_index"])
                ] = int(count_row["votes"])
        polls = []
        for row in rows:
            poll = dict(row)
            try:
                poll["options"] = json.loads(poll.pop("options_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                poll["options"] = []
            counts = vote_counts.get(int(poll["id"]), {})
            poll["results"] = [
                {"option_index": index, "option": option, "votes": counts.get(index, 0)}
                for index, option in enumerate(poll["options"])
            ]
            polls.append(poll)
        return _tool_text(req_id, {"count": len(polls), "limit": limit, "offset": offset, "polls": polls})

    if normalized_name == "list_user_statistics":
        username = str(arguments.get("username") or "").strip()
        include_email = _as_bool_or_none(arguments.get("include_email", False))
        if include_email is None:
            return _error(req_id, -32602, "Invalid params: include_email must be boolean")
        sort_by = str(arguments.get("sort_by") or "participation").strip().lower()
        sort_direction = str(arguments.get("sort_direction") or "desc").strip().lower()
        if "username" in arguments and not username:
            return _error(req_id, -32602, "Invalid params: username must not be empty")
        if sort_by not in {
            "participation", "proposed_budget", "approved_budget",
            "approved_budget_percentage", "poll_count", "created_poll_vote_count",
            "average_votes_per_created_poll", "group_purchase_count",
            "created_group_purchase_order_value", "created_group_purchase_participant_count", "username",
        }:
            return _error(req_id, -32602, "Invalid params: unknown sort_by value")
        if sort_direction not in {"asc", "desc"}:
            return _error(req_id, -32602, "Invalid params: sort_direction must be asc or desc")
        limit, offset, pagination_error = _paginate(req_id, arguments, default_limit=100, max_limit=500)
        if pagination_error:
            return pagination_error

        query, query_params = user_statistics_query(
            limit,
            offset,
            username=username or None,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
        rows = _db_rows(query, query_params)
        total_query, total_params = user_statistics_total_query(username or None)
        total_rows = _db_rows(total_query, total_params)
        total = int(total_rows[0]["total"]) if total_rows else 0
        return _tool_text(
            req_id,
            {
                "count": len(rows),
                "total": total,
                "limit": limit,
                "offset": offset,
                "users": user_statistics_rows(rows, include_email=include_email),
            },
        )

    if normalized_name == "list_group_purchases":
        status = str(arguments.get("status") or "").strip().lower()
        username = str(arguments.get("username") or "").strip()
        if "status" in arguments and not status:
            return _error(req_id, -32602, "Invalid params: status must not be empty")
        if status and status not in VALID_GROUP_PURCHASE_STATUSES:
            return _error(req_id, -32602, "Invalid params: unknown group purchase status")
        if "username" in arguments and not username:
            return _error(req_id, -32602, "Invalid params: username must not be empty")
        limit, offset, pagination_error = _paginate(req_id, arguments, default_limit=20, max_limit=200)
        if pagination_error:
            return pagination_error
        conditions: list[str] = []
        query_params: list[Any] = []
        if status:
            conditions.append("gp.status = ?")
            query_params.append(status)
        if username:
            conditions.append("m.username = ? COLLATE NOCASE")
            query_params.append(username)
        query = """
            SELECT gp.id,gp.title,gp.description,gp.status,gp.created_at,gp.deadline,gp.url,
                   gp.payment_method,gp.created_by,m.username
            FROM group_purchases gp JOIN members m ON m.id = gp.created_by
        """
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY gp.created_at DESC LIMIT ? OFFSET ?"
        rows = _db_rows(query, tuple(query_params) + (limit, offset))
        purchases = []
        for row in rows:
            purchase = dict(row)
            purchase_id = int(purchase["id"])
            components = _db_rows(
                """SELECT c.id,c.name,c.unit_price,COALESCE(SUM(q.quantity),0) AS total_quantity
                   FROM group_purchase_components c
                   LEFT JOIN group_purchase_quantities q ON q.component_id = c.id
                   WHERE c.group_purchase_id = ? GROUP BY c.id ORDER BY c.position,c.id""",
                (purchase_id,),
            )
            shared_costs = _db_rows(
                "SELECT label,amount FROM group_purchase_shared_costs WHERE group_purchase_id = ? ORDER BY position,id",
                (purchase_id,),
            )
            participants = _db_rows(
                """SELECT m.id AS member_id,m.username,SUM(q.quantity*c.unit_price) AS selection_amount,
                          CASE WHEN pp.member_id IS NULL THEN 0 ELSE 1 END AS paid
                   FROM group_purchase_quantities q
                   JOIN group_purchase_components c ON c.id = q.component_id
                   JOIN members m ON m.id = q.member_id
                   LEFT JOIN group_purchase_payments pp
                     ON pp.group_purchase_id = c.group_purchase_id AND pp.member_id = m.id
                   WHERE c.group_purchase_id = ? AND q.quantity > 0
                   GROUP BY m.id,m.username,pp.member_id ORDER BY m.username COLLATE NOCASE""",
                (purchase_id,),
            )
            shared_total = sum(float(cost["amount"]) for cost in shared_costs)
            selection_total = sum(float(person["selection_amount"] or 0) for person in participants)
            allocated = 0.0
            for index, person in enumerate(participants):
                selection = float(person["selection_amount"] or 0)
                if selection_total and index == len(participants) - 1:
                    share = round(shared_total - allocated, 2)
                else:
                    share = round(shared_total * selection / selection_total, 2) if selection_total else 0
                    allocated += share
                person["shared_cost_share"] = share
                person["amount_owed"] = round(selection + share, 2)
            purchase["components"] = components
            purchase["shared_costs"] = shared_costs
            purchase["shared_cost_total"] = round(shared_total, 2)
            purchase["selection_total"] = round(selection_total, 2)
            purchase["total_cost"] = round(selection_total + shared_total, 2)
            purchase["participants"] = participants
            purchase["participant_count"] = len(participants)
            purchase["paid_participant_count"] = sum(int(person["paid"]) for person in participants)
            purchases.append(purchase)
        return _tool_text(
            req_id,
            {"count": len(purchases), "limit": limit, "offset": offset, "group_purchases": purchases},
        )

    if normalized_name == "current_budget":
        rows = _db_rows("SELECT value FROM settings WHERE key='current_budget' LIMIT 1")
        value = rows[0]["value"] if rows else None
        return _tool_text(req_id, {"current_budget": value})


    if normalized_name == "list_member_telegram_links":
        include_unlinked = _as_bool_or_none(arguments.get("include_unlinked", False))
        if include_unlinked is None:
            return _error(req_id, -32602, "Invalid params: include_unlinked must be boolean")
        limit, offset, pagination_error = _paginate(req_id, arguments, default_limit=200, max_limit=500)
        if pagination_error:
            return pagination_error

        if include_unlinked:
            rows = _db_rows(
                """
                SELECT id, username, telegram_username, telegram_user_id, last_linked_at, last_unlinked_at,
                       CASE WHEN {linked_condition} THEN 1 ELSE 0 END AS linked,
                       {link_state_case} AS link_state
                FROM members
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """.format(linked_condition=LINKED_CONDITION_SQL, link_state_case=link_state_case_sql()),
                (limit, offset),
            )
        else:
            rows = _db_rows(
                """
                SELECT id, username, telegram_username, telegram_user_id, last_linked_at, last_unlinked_at,
                       1 AS linked, 'linked' AS link_state
                FROM members
                WHERE {linked_condition}
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """.format(linked_condition=LINKED_CONDITION_SQL),
                (limit, offset),
            )
        return _tool_text(req_id, {"count": len(rows), "limit": limit, "offset": offset, "members": rows})

    if normalized_name == "get_voting_settings":
        return _tool_text(req_id, _read_voting_settings())

    if normalized_name == "update_voting_settings":
        poll_vote_mode = arguments.get("poll_vote_mode")
        proposal_vote_mode = arguments.get("proposal_vote_mode")
        linked_required = arguments.get("telegram_require_linked_vote")
        if poll_vote_mode is None and proposal_vote_mode is None and linked_required is None:
            return _error(req_id, -32602, "Invalid params: at least one setting must be provided")
        if poll_vote_mode is not None and str(poll_vote_mode) not in VALID_VOTE_MODES:
            return _error(req_id, -32602, "Invalid params: poll_vote_mode is invalid")
        if proposal_vote_mode is not None and str(proposal_vote_mode) not in VALID_VOTE_MODES:
            return _error(req_id, -32602, "Invalid params: proposal_vote_mode is invalid")
        linked_required_bool = _as_bool_or_none(linked_required)
        if linked_required is not None and linked_required_bool is None:
            return _error(req_id, -32602, "Invalid params: telegram_require_linked_vote must be boolean")

        conn = sqlite3.connect(DB_PATH)
        try:
            voting_settings_service.apply_voting_settings(
                conn,
                poll_vote_mode=str(poll_vote_mode) if poll_vote_mode is not None else None,
                proposal_vote_mode=str(proposal_vote_mode) if proposal_vote_mode is not None else None,
                telegram_require_linked_vote=linked_required_bool if linked_required is not None else None,
            )
        finally:
            conn.close()
        return _tool_text(req_id, _read_voting_settings())

    if normalized_name == "create_member":
        username = str(arguments.get("username") or "").strip()
        password = str(arguments.get("password") or "")
        is_admin = _as_bool_or_none(arguments.get("is_admin", False))
        if not username or not password:
            return _error(req_id, -32602, "Invalid params: username and password are required")
        if is_admin is None:
            return _error(req_id, -32602, "Invalid params: is_admin must be boolean")
        exists = _db_rows("SELECT id FROM members WHERE username = ? LIMIT 1", (username,))
        if exists:
            return _error(req_id, -32010, "Conflict: username already exists")
        member_id = _db_execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), 1 if is_admin else 0),
        )
        return _tool_text(req_id, {"success": True, "member_id": member_id, "username": username})

    if normalized_name == "create_feedback":
        try:
            member_id = int(arguments.get("member_id"))
        except (TypeError, ValueError):
            return _error(req_id, -32602, "Invalid params: member_id must be an integer")
        conn = sqlite3.connect(DB_PATH)
        try:
            feedback_id = feedback_service.submit_feedback(
                conn, member_id=member_id, source="telegram",
                category=arguments.get("category"), message=arguments.get("message"), logger=logger,
            )
        except feedback_service.FeedbackValidationError as exc:
            return _error(req_id, -32004 if exc.code == "member_not_found" else -32602, f"{exc.code}: {exc}")
        finally:
            conn.close()
        return _tool_text(req_id, {"success": True, "feedback_id": feedback_id})

    if normalized_name == "create_proposal":
        title = str(arguments.get("title") or "").strip()
        description = str(arguments.get("description") or "")
        url = str(arguments.get("url") or "")
        basic_supplies_value = _as_bool_or_none(arguments.get("basic_supplies", False))
        if basic_supplies_value is None:
            return _error(req_id, -32602, "Invalid params: basic_supplies must be boolean")
        basic_supplies = 1 if basic_supplies_value else 0
        created_by = arguments.get("created_by")
        amount = arguments.get("amount")
        if not title or created_by is None or amount is None:
            return _error(req_id, -32602, "Invalid params: title, amount, and created_by are required")
        try:
            amount_val = float(amount)
            created_by_val = int(created_by)
        except (TypeError, ValueError):
            return _error(req_id, -32602, "Invalid params: amount/created_by types are invalid")
        if amount_val <= 0:
            return _error(req_id, -32602, "Invalid params: amount must be positive")
        member = _db_rows("SELECT id FROM members WHERE id = ? LIMIT 1", (created_by_val,))
        if not member:
            return _error(req_id, -32004, "Not found: creator member not found")
        image_filename = None
        if arguments.get("image") is not None:
            try:
                image_filename = _save_proposal_image(arguments["image"])
            except (OSError, ValueError) as exc:
                return _error(req_id, -32602, f"Invalid params: {exc}")
        try:
            proposal_id = _create_proposal_record(
                title, description, amount_val, url, created_by_val, basic_supplies, image_filename
            )
        except sqlite3.IntegrityError as exc:
            _remove_uploaded_image(image_filename)
            return _error(req_id, -32011, f"Conflict: create_proposal failed integrity checks ({exc})")
        except sqlite3.OperationalError as exc:
            _remove_uploaded_image(image_filename)
            return _error(req_id, -32012, f"Unavailable: create_proposal database operation failed ({exc})")
        payload = {"success": True, "proposal_id": proposal_id, "url": url, "image_filename": image_filename}
        if alias_warning:
            payload["warning"] = alias_warning
        return _tool_text(req_id, payload)

    if normalized_name == "create_poll":
        question = str(arguments.get("question") or "").strip()
        options = arguments.get("options")
        created_by = arguments.get("created_by")
        if not question or not isinstance(options, list) or created_by is None:
            return _error(req_id, -32602, "Invalid params: question, options, and created_by are required")
        if len(question) < 5 or len(question) > 200:
            return _error(req_id, -32602, "Invalid params: question must be 5..200 characters")
        cleaned = normalize_poll_options(options)
        if cleaned is None:
            return _error(
                req_id,
                -32602,
                "Invalid params: options must contain 2..12 non-empty values of at most 120 characters each",
            )
        try:
            created_by_val = int(created_by)
        except (TypeError, ValueError):
            return _error(req_id, -32602, "Invalid params: created_by must be an integer")
        member = _db_rows("SELECT id FROM members WHERE id = ? LIMIT 1", (created_by_val,))
        if not member:
            return _error(req_id, -32004, "Not found: creator member not found")
        conn = sqlite3.connect(DB_PATH)
        try:
            poll_id = PollRepository(conn).create(question, cleaned, created_by_val)
        finally:
            conn.close()
        return _tool_text(req_id, {"success": True, "poll_id": poll_id})

    return _error(req_id, -32601, f"Unknown tool: {tool_name}")

def handle_request(req: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any] | None:
    req_id = req.get("id")
    if req.get("jsonrpc") != "2.0":
        return _error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = req.get("method")
    if not isinstance(method, str) or not method:
        return _error(req_id, -32600, "Invalid Request: method is required")

    if req_id is None and method in {"notifications/initialized"}:
        return None

    params = req.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(req_id, -32602, "Invalid params: params must be an object")

    if not _authorized(req, method, headers):
        return _error(req_id, -32001, "Unauthorized: invalid or missing MCP api_key")

    if method == "initialize":
        return _result(req_id, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "manavote-mcp", "version": "0.3.0"}, "capabilities": {"tools": {}}})

    if method == "tools/list":
        return _result(req_id, {"tools": tool_definitions()})

    if method == "tools/call":
        tool_name = params.get("name")
        if tool_name is None:
            tool_name = params.get("tool_name") or params.get("tool")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        return mcp_application.execute_tool(
            execute_tool_command, tool_name, arguments,
            actor=mcp_application.Actor.system(), req_id=req_id,
        )

    return _error(req_id, -32601, f"Unknown method: {method}")


def _process_jsonrpc_body(body: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    try:
        req = json.loads(body)
    except json.JSONDecodeError:
        return 400, json.dumps(_error(None, -32700, "Parse error")).encode("utf-8")

    if isinstance(req, list):
        if not req:
            return 400, json.dumps(_error(None, -32600, "Invalid Request")).encode("utf-8")
        responses: list[dict[str, Any]] = []
        for item in req:
            if not isinstance(item, dict):
                responses.append(_error(None, -32600, "Invalid Request"))
                continue
            item_id = item.get("id")
            try:
                resp = handle_request(item, headers=headers)
            except MCP_APPLICATION_FAILURES:
                logger.exception(
                    "mcp_request_failure reason_code=application_failure request_id=%s",
                    item_id,
                )
                resp = _error(item_id, -32000, "Internal server error")
            if resp is not None:
                responses.append(resp)
        if not responses:
            return 202, b"{}"
        return 200, json.dumps(responses).encode("utf-8")

    if not isinstance(req, dict):
        return 400, json.dumps(_error(None, -32600, "Invalid Request: body must be an object")).encode("utf-8")

    req_id = req.get("id") if isinstance(req, dict) else None
    try:
        resp = handle_request(req, headers=headers)
    except MCP_APPLICATION_FAILURES:
        logger.exception(
            "mcp_request_failure reason_code=application_failure request_id=%s", req_id
        )
        return 500, json.dumps(_error(req_id, -32000, "Internal server error")).encode("utf-8")
    if resp is None:
        return 202, b"{}"
    return 200, json.dumps(resp).encode("utf-8")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        status, payload = _process_jsonrpc_body(line)
        if status in {200, 400, 500}:
            sys.stdout.write(payload.decode("utf-8") + "\n")
            sys.stdout.flush()


class _TCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        for raw in self.rfile:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                resp = _error(None, -32700, "Parse error")
            else:
                try:
                    resp = (
                        handle_request(req)
                        if isinstance(req, dict)
                        else _error(None, -32600, "Invalid Request")
                    )
                except MCP_APPLICATION_FAILURES:
                    logger.exception(
                        "mcp_request_failure reason_code=application_failure transport=tcp"
                    )
                    resp = _error(None, -32000, "Internal server error")
            if resp is not None:
                self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))


class _HTTPHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ManaVoteMCP/0.1"

    def do_POST(self):
        if self.path != "/mcp":
            self.send_error(404, "Not Found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        lowered_headers = {k.lower(): v for k, v in self.headers.items()}
        status, payload = _process_jsonrpc_body(body, headers=lowered_headers)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args: Any) -> None:
        logging.getLogger(__name__).debug("mcp-http " + format, *args)


def start_tcp_server(host: str = "127.0.0.1", port: int = 8765):
    server = socketserver.ThreadingTCPServer((host, port), _TCPHandler)
    logging.getLogger(__name__).info("MCP server listening on %s:%s", host, port)
    server.serve_forever()


def start_http_server(host: str = "127.0.0.1", port: int = 8765):
    server = http.server.ThreadingHTTPServer((host, port), _HTTPHandler)
    logging.getLogger(__name__).info("MCP HTTP server listening on http://%s:%s/mcp", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
