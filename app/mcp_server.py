"""Lightweight MCP server for ManaVote admin data (JSON-RPC)."""

from __future__ import annotations

import json
import http.server
import logging
import os
import socketserver
import sqlite3
import sys
from typing import Any
from werkzeug.security import generate_password_hash
from app.services.telegram_link_diagnostics import LINKED_CONDITION_SQL, link_state_case_sql

DB_PATH = os.getenv("APP_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db"))
MCP_API_KEY = os.getenv("MCP_API_KEY", "")
VALID_PROPOSAL_STATUSES = {"active", "accepted", "rejected", "purchased"}
VALID_VOTE_MODES = {"both", "web_only", "telegram_only"}


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
    params = req.get("params") or {}
    body_key = params.get("api_key")
    provided = header_key or (body_key if isinstance(body_key, str) else "")
    return bool(MCP_API_KEY) and provided == MCP_API_KEY


def handle_request(req: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any] | None:
    req_id = req.get("id")
    if req.get("jsonrpc") != "2.0":
        return _error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = req.get("method")
    if not isinstance(method, str) or not method:
        return _error(req_id, -32600, "Invalid Request: method is required")

    if req_id is None and method in {"notifications/initialized"}:
        return None

    if not _authorized(req, method, headers):
        return _error(req_id, -32001, "Unauthorized: invalid or missing MCP api_key")

    if method == "initialize":
        return _result(req_id, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "manavote-mcp", "version": "0.3.0"}, "capabilities": {"tools": {}}})

    if method == "tools/list":
        return _result(req_id, {"tools": [{"name": "list_proposals", "description": "List latest proposals, optionally filtered by status.", "inputSchema": {"type": "object", "properties": {"status": {"type": "string", "enum": sorted(VALID_PROPOSAL_STATUSES)}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}}}}, {"name": "current_budget", "description": "Get configured current budget setting.", "inputSchema": {"type": "object", "properties": {}}}, {"name": "list_member_telegram_links", "description": "List members and Telegram link information.", "inputSchema": {"type": "object", "properties": {"include_unlinked": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}, "offset": {"type": "integer", "minimum": 0}}}}, {"name": "get_voting_settings", "description": "Get current voting settings.", "inputSchema": {"type": "object", "properties": {}}}, {"name": "update_voting_settings", "description": "Update voting settings.", "inputSchema": {"type": "object", "properties": {"poll_vote_mode": {"type": "string", "enum": sorted(VALID_VOTE_MODES)}, "proposal_vote_mode": {"type": "string", "enum": sorted(VALID_VOTE_MODES)}, "telegram_require_linked_vote": {"type": "boolean"}}}}, {"name": "create_member", "description": "Create a member (admin-only action).", "inputSchema": {"type": "object", "required": ["username", "password"], "properties": {"username": {"type": "string", "minLength": 1}, "password": {"type": "string", "minLength": 1}, "is_admin": {"type": "boolean"}}}}, {"name": "create_proposal", "description": "Create a proposal (admin-only action).", "inputSchema": {"type": "object", "required": ["title", "amount", "created_by"], "properties": {"title": {"type": "string", "minLength": 1}, "description": {"type": "string"}, "amount": {"type": "number", "exclusiveMinimum": 0}, "url": {"type": "string"}, "basic_supplies": {"type": "boolean"}, "created_by": {"type": "integer", "minimum": 1}}}}, {"name": "create_poll", "description": "Create a poll (admin-only action).", "inputSchema": {"type": "object", "required": ["question", "options", "created_by"], "properties": {"question": {"type": "string", "minLength": 5, "maxLength": 200}, "options": {"type": "array", "minItems": 2, "maxItems": 12, "items": {"type": "string"}}, "created_by": {"type": "integer", "minimum": 1}}}}]})

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return _error(req_id, -32602, "Invalid params: tool name is required")
        if not isinstance(arguments, dict):
            return _error(req_id, -32602, "Invalid params: arguments must be an object")

        if name == "list_proposals":
            status = str(arguments.get("status") or "").strip().lower()
            if status and status not in VALID_PROPOSAL_STATUSES:
                return _error(req_id, -32602, "Invalid params: unknown status filter")
            try:
                limit = int(arguments.get("limit") or 20)
                offset = int(arguments.get("offset") or 0)
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: limit/offset must be integers")
            if offset < 0:
                return _error(req_id, -32602, "Invalid params: offset must be >= 0")
            limit = max(1, min(limit, 200))
            query = "SELECT id,title,description,amount,status,created_at FROM proposals"
            query_params: tuple[Any, ...] = ()
            if status:
                query += " WHERE status = ?"
                query_params = (status,)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            rows = _db_rows(query, query_params + (limit, offset))
            return _tool_text(req_id, {"count": len(rows), "limit": limit, "offset": offset, "proposals": rows})

        if name == "current_budget":
            rows = _db_rows("SELECT value FROM settings WHERE key='current_budget' LIMIT 1")
            value = rows[0]["value"] if rows else None
            return _tool_text(req_id, {"current_budget": value})


        if name == "list_member_telegram_links":
            include_unlinked = bool(arguments.get("include_unlinked", False))
            try:
                limit = int(arguments.get("limit") or 200)
                offset = int(arguments.get("offset") or 0)
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: limit/offset must be integers")
            if offset < 0:
                return _error(req_id, -32602, "Invalid params: offset must be >= 0")
            if limit < 1 or limit > 500:
                return _error(req_id, -32602, "Invalid params: limit must be between 1 and 500")

            if include_unlinked:
                rows = _db_rows(
                    """
                    SELECT id, username, telegram_username, telegram_user_id,
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
                    SELECT id, username, telegram_username, telegram_user_id, 1 AS linked, 'linked' AS link_state
                    FROM members
                    WHERE {linked_condition}
                    ORDER BY id ASC
                    LIMIT ? OFFSET ?
                    """.format(linked_condition=LINKED_CONDITION_SQL),
                    (limit, offset),
                )
            return _tool_text(req_id, {"count": len(rows), "limit": limit, "offset": offset, "members": rows})

        if name == "get_voting_settings":
            return _tool_text(req_id, _read_voting_settings())

        if name == "update_voting_settings":
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

        if name == "create_member":
            username = str(arguments.get("username") or "").strip()
            password = str(arguments.get("password") or "")
            is_admin = bool(arguments.get("is_admin", False))
            if not username or not password:
                return _error(req_id, -32602, "Invalid params: username and password are required")
            exists = _db_rows("SELECT id FROM members WHERE username = ? LIMIT 1", (username,))
            if exists:
                return _error(req_id, -32010, "Conflict: username already exists")
            member_id = _db_execute(
                "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), 1 if is_admin else 0),
            )
            return _tool_text(req_id, {"success": True, "member_id": member_id, "username": username})

        if name == "create_proposal":
            title = str(arguments.get("title") or "").strip()
            description = str(arguments.get("description") or "")
            url = str(arguments.get("url") or "")
            basic_supplies = 1 if bool(arguments.get("basic_supplies", False)) else 0
            created_by = arguments.get("created_by")
            amount = arguments.get("amount")
            if not title or created_by is None or amount is None:
                return _error(req_id, -32602, "Invalid params: title, amount, and created_by are required")
            try:
                amount_val = float(amount)
                created_by_val = int(created_by)
            except (TypeError, ValueError):
                return _error(req_id, -32602, "Invalid params: amount/created_by types are invalid")
            if amount_val <= 0 or created_by_val <= 0:
                return _error(req_id, -32602, "Invalid params: amount and created_by must be positive")
            member = _db_rows("SELECT id FROM members WHERE id = ? LIMIT 1", (created_by_val,))
            if not member:
                return _error(req_id, -32004, "Not found: creator member not found")
            proposal_id = _create_proposal_record(title, description, amount_val, url, created_by_val, basic_supplies)
            return _tool_text(req_id, {"success": True, "proposal_id": proposal_id})

        if name == "create_poll":
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

        return _error(req_id, -32601, f"Unknown tool: {name}")

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
            resp = handle_request(item, headers=headers)
            if resp is not None:
                responses.append(resp)
        if not responses:
            return 202, b"{}"
        return 200, json.dumps(responses).encode("utf-8")

    if not isinstance(req, dict):
        return 400, json.dumps(_error(None, -32600, "Invalid Request: body must be an object")).encode("utf-8")

    try:
        resp = handle_request(req, headers=headers)
    except Exception as exc:
        return 500, json.dumps(_error(None, -32000, f"Server error: {exc}")).encode("utf-8")
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
