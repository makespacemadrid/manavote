"""Lightweight MCP server for ManaVote admin data (JSON-RPC)."""

from __future__ import annotations

import hmac
import http.server
import json
import logging
import os
import socketserver
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from werkzeug.security import generate_password_hash

from app.domain.enums import ProposalStatus
from app.services.telegram_link_diagnostics import LINKED_CONDITION_SQL, link_state_case_sql
from app.services.user_statistics import user_statistics_query, user_statistics_rows, user_statistics_total_query

DB_PATH = os.getenv("APP_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db"))
MCP_API_KEY = os.getenv("MCP_API_KEY", "")
VALID_PROPOSAL_STATUSES = {status.value for status in ProposalStatus}
VALID_VOTE_MODES = {"both", "web_only", "telegram_only"}
VALID_GROUP_PURCHASE_STATUSES = {"open", "ordered", "received"}
TOOL_ALIASES = {"crreate_proposal": "create_proposal"}


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
) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO proposals (title, description, amount, url, created_by, basic_supplies) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, amount_val, url, created_by_val, basic_supplies),
        )
        proposal_id = int(cur.lastrowid or 0)
        if basic_supplies and amount_val > 20.0:
            cur.execute("UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,))
            cur.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (proposal_id, created_by_val, "Auto-removed basic supplies flag: amount over €20"),
            )
        conn.commit()
        return proposal_id
    finally:
        conn.close()


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


def _tool_definitions() -> list[dict[str, Any]]:
    """Return the MCP discovery contract in a reviewable structure."""

    return [
        {
            "name": "list_proposals",
            "description": "List latest proposals, optionally filtered by status and age.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": sorted(VALID_PROPOSAL_STATUSES)},
                    "age": {
                        "type": "string",
                        "enum": ["recent", "old"],
                        "description": "Active proposals newer than 30 days (recent) or at least 30 days old (old).",
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
            "description": "Create a proposal (admin-only action).",
            "inputSchema": {
                "type": "object",
                "required": ["title", "amount", "created_by"],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "description": {"type": "string"},
                    "amount": {"type": "number", "exclusiveMinimum": 0},
                    "url": {"type": "string"},
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
        return _result(req_id, {"tools": _tool_definitions()})

    if method == "tools/call":
        tool_name = params.get("name")
        if tool_name is None:
            # Compatibility alias for clients that avoid placing `name` in
            # logging extras because Python logging treats it as a reserved
            # LogRecord attribute.
            tool_name = params.get("tool_name") or params.get("tool")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(tool_name, str):
            return _error(req_id, -32602, "Invalid params: tool name is required")
        normalized_name = TOOL_ALIASES.get(tool_name, tool_name)
        alias_warning = None
        if normalized_name != tool_name:
            alias_warning = f"Deprecated tool alias '{tool_name}' used; please use '{normalized_name}'"
        if not isinstance(arguments, dict):
            return _error(req_id, -32602, "Invalid params: arguments must be an object")

        if normalized_name == "list_proposals":
            status = str(arguments.get("status") or "").strip().lower()
            age = str(arguments.get("age") or "").strip().lower()
            username = str(arguments.get("username") or "").strip()
            if "username" in arguments and not username:
                return _error(req_id, -32602, "Invalid params: username must not be empty")
            if status and status not in VALID_PROPOSAL_STATUSES:
                return _error(req_id, -32602, "Invalid params: unknown status filter")
            if age not in {"", "recent", "old"}:
                return _error(req_id, -32602, "Invalid params: age must be recent or old")
            if age and status and status != "active":
                return _error(req_id, -32602, "Invalid params: age can only be combined with status=active")
            try:
                limit = int(arguments["limit"]) if "limit" in arguments else 20
                offset = int(arguments["offset"]) if "offset" in arguments else 0
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: limit/offset must be integers")
            if limit < 1 or limit > 200:
                return _error(req_id, -32602, "Invalid params: limit must be between 1 and 200")
            if offset < 0:
                return _error(req_id, -32602, "Invalid params: offset must be >= 0")
            query = (
                "SELECT p.id,p.title,p.description,p.amount,p.status,p.created_at,p.created_by,m.username "
                "FROM proposals p JOIN members m ON m.id = p.created_by"
            )
            conditions: list[str] = []
            query_params: list[Any] = []
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
            return _tool_text(req_id, {"count": len(rows), "limit": limit, "offset": offset, "proposals": rows})

        if normalized_name == "list_polls":
            status = str(arguments.get("status") or "").strip().lower()
            username = str(arguments.get("username") or "").strip()
            if status not in {"", "open", "closed"}:
                return _error(req_id, -32602, "Invalid params: poll status must be open or closed")
            if "username" in arguments and not username:
                return _error(req_id, -32602, "Invalid params: username must not be empty")
            try:
                limit = int(arguments["limit"]) if "limit" in arguments else 20
                offset = int(arguments["offset"]) if "offset" in arguments else 0
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: limit/offset must be integers")
            if limit < 1 or limit > 200:
                return _error(req_id, -32602, "Invalid params: limit must be between 1 and 200")
            if offset < 0:
                return _error(req_id, -32602, "Invalid params: offset must be >= 0")
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
            try:
                limit = int(arguments["limit"]) if "limit" in arguments else 100
                offset = int(arguments["offset"]) if "offset" in arguments else 0
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: limit/offset must be integers")
            if limit < 1 or limit > 500:
                return _error(req_id, -32602, "Invalid params: limit must be between 1 and 500")
            if offset < 0:
                return _error(req_id, -32602, "Invalid params: offset must be >= 0")

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
            try:
                limit = int(arguments["limit"]) if "limit" in arguments else 20
                offset = int(arguments["offset"]) if "offset" in arguments else 0
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: limit/offset must be integers")
            if limit < 1 or limit > 200:
                return _error(req_id, -32602, "Invalid params: limit must be between 1 and 200")
            if offset < 0:
                return _error(req_id, -32602, "Invalid params: offset must be >= 0")
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
            try:
                limit = int(arguments["limit"]) if "limit" in arguments else 200
                offset = int(arguments["offset"]) if "offset" in arguments else 0
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: limit/offset must be integers")
            if offset < 0:
                return _error(req_id, -32602, "Invalid params: offset must be >= 0")
            if limit < 1 or limit > 500:
                return _error(req_id, -32602, "Invalid params: limit must be between 1 and 500")

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
                cur = conn.cursor()
                if poll_vote_mode is not None:
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('poll_vote_mode', ?)", (str(poll_vote_mode),))
                if proposal_vote_mode is not None:
                    cur.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES ('proposal_vote_mode', ?)", (str(proposal_vote_mode),)
                    )
                if linked_required is not None:
                    cur.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_require_linked_vote', ?)",
                        ("true" if linked_required_bool else "false",),
                    )
                conn.commit()
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
            try:
                proposal_id = _create_proposal_record(title, description, amount_val, url, created_by_val, basic_supplies)
            except sqlite3.IntegrityError as exc:
                return _error(req_id, -32011, f"Conflict: create_proposal failed integrity checks ({exc})")
            except sqlite3.OperationalError as exc:
                return _error(req_id, -32012, f"Unavailable: create_proposal database operation failed ({exc})")
            payload = {"success": True, "proposal_id": proposal_id}
            if alias_warning:
                payload["warning"] = alias_warning
            return _tool_text(req_id, payload)

        if normalized_name == "create_poll":
            question = str(arguments.get("question") or "").strip()
            options = arguments.get("options")
            created_by = arguments.get("created_by")
            if not question or not isinstance(options, list) or created_by is None:
                return _error(req_id, -32602, "Invalid params: question, options, and created_by are required")
            cleaned = [str(opt).strip() for opt in options if str(opt).strip()]
            if len(cleaned) < 2 or len(cleaned) > 12:
                return _error(req_id, -32602, "Invalid params: options must contain 2..12 non-empty values")
            if len(question) < 5 or len(question) > 200:
                return _error(req_id, -32602, "Invalid params: question must be 5..200 characters")
            if any(len(opt) > 120 for opt in cleaned):
                return _error(req_id, -32602, "Invalid params: each option must be <= 120 characters")
            try:
                created_by_val = int(created_by)
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: created_by must be an integer")
            member = _db_rows("SELECT id FROM members WHERE id = ? LIMIT 1", (created_by_val,))
            if not member:
                return _error(req_id, -32004, "Not found: creator member not found")
            poll_id = _db_execute(
                "INSERT INTO polls (question, options_json, created_by, status) VALUES (?, ?, ?, 'open')",
                (question, json.dumps(cleaned), created_by_val),
            )
            return _tool_text(req_id, {"success": True, "poll_id": poll_id})

        return _error(req_id, -32601, f"Unknown tool: {tool_name}")

    return _error(req_id, -32601, f"Unknown method: {method}")


def _process_jsonrpc_body(body: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    try:
        req = json.loads(body)
    except json.JSONDecodeError:
        return 400, json.dumps(_error(None, -32700, "Parse error")).encode("utf-8")
    except Exception as exc:
        return 500, json.dumps(_error(None, -32000, f"Server error: {exc}")).encode("utf-8")

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
            except Exception as exc:
                resp = _error(item_id, -32000, f"Server error: {exc}")
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
    except Exception as exc:
        return 500, json.dumps(_error(req_id, -32000, f"Server error: {exc}")).encode("utf-8")
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
                resp = handle_request(req) if isinstance(req, dict) else _error(None, -32600, "Invalid Request")
            except Exception as exc:
                resp = _error(None, -32000, f"Server error: {exc}")
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
