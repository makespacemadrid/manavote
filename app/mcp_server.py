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

DB_PATH = os.getenv("APP_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db"))
MCP_API_KEY = os.getenv("MCP_API_KEY", "")
VALID_PROPOSAL_STATUSES = {"active", "accepted", "rejected", "purchased"}


def _db_rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _tool_text(req_id: Any, payload: Any) -> dict[str, Any]:
    return _result(req_id, {"content": [{"type": "text", "text": json.dumps(payload)}]})


def _authorized(req: dict[str, Any], method: str) -> bool:
    if method == "notifications/initialized":
        return True
    params = req.get("params") or {}
    provided = params.get("api_key")
    return bool(MCP_API_KEY) and isinstance(provided, str) and provided == MCP_API_KEY


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    req_id = req.get("id")
    if req.get("jsonrpc") != "2.0":
        return _error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = req.get("method")
    if not isinstance(method, str) or not method:
        return _error(req_id, -32600, "Invalid Request: method is required")

    if req_id is None and method in {"notifications/initialized"}:
        return None

    if not _authorized(req, method):
        return _error(req_id, -32001, "Unauthorized: invalid or missing MCP api_key")

    if method == "initialize":
        return _result(req_id, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "manavote-mcp", "version": "0.3.0"}, "capabilities": {"tools": {}}})

    if method == "tools/list":
        return _result(req_id, {"tools": [{"name": "list_proposals", "description": "List latest proposals, optionally filtered by status.", "inputSchema": {"type": "object", "properties": {"status": {"type": "string", "enum": sorted(VALID_PROPOSAL_STATUSES)}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}}}}, {"name": "current_budget", "description": "Get configured current budget setting.", "inputSchema": {"type": "object", "properties": {}}}, {"name": "list_member_telegram_links", "description": "List members and Telegram link information.", "inputSchema": {"type": "object", "properties": {"include_unlinked": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}, "offset": {"type": "integer", "minimum": 0}}}}]})

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
            limit = max(1, min(limit, 500))

            if include_unlinked:
                rows = _db_rows(
                    """
                    SELECT id, username, telegram_username, telegram_user_id,
                           CASE WHEN telegram_username IS NOT NULL AND telegram_username != '' AND telegram_user_id IS NOT NULL THEN 1 ELSE 0 END AS linked
                    FROM members
                    ORDER BY id ASC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            else:
                rows = _db_rows(
                    """
                    SELECT id, username, telegram_username, telegram_user_id, 1 AS linked
                    FROM members
                    WHERE telegram_username IS NOT NULL AND telegram_username != '' AND telegram_user_id IS NOT NULL
                    ORDER BY id ASC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            return _tool_text(req_id, {"count": len(rows), "limit": limit, "offset": offset, "members": rows})

        return _error(req_id, -32601, f"Unknown tool: {name}")

    return _error(req_id, -32601, f"Unknown method: {method}")


def _process_jsonrpc_body(body: str) -> tuple[int, bytes]:
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
            resp = handle_request(item)
            if resp is not None:
                responses.append(resp)
        if not responses:
            return 202, b"{}"
        return 200, json.dumps(responses).encode("utf-8")

    if not isinstance(req, dict):
        return 400, json.dumps(_error(None, -32600, "Invalid Request: body must be an object")).encode("utf-8")

    try:
        resp = handle_request(req)
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
        status, payload = _process_jsonrpc_body(body)
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
