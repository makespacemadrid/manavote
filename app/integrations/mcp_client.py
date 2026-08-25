"""Small JSON-RPC client used by the Telegram MCP command bridge."""

import itertools
import json
import threading

import requests


class MCPClientError(RuntimeError):
    """Raised when an MCP server cannot return a usable result."""


class MCPClient:
    def __init__(self, url, api_key, timeout=10, session=None):
        self.url = (url or "").strip()
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.session = session or requests.Session()
        self._request_ids = itertools.count(1)
        self._initialized = False
        self._session_id = None
        self._initialize_lock = threading.Lock()

    @property
    def configured(self):
        return bool(self.url and self.api_key)

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Api-Key": self.api_key,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, payload, expect_result=True):
        if not self.configured:
            raise MCPClientError("MCP is not configured")
        try:
            response = self.session.post(self.url, headers=self._headers(), json=payload, timeout=self.timeout)
            response.raise_for_status()
            session_id = response.headers.get("Mcp-Session-Id") if hasattr(response, "headers") else None
            if session_id:
                self._session_id = session_id
            if not expect_result:
                return None
            content_type = response.headers.get("Content-Type", "") if hasattr(response, "headers") else ""
            if "text/event-stream" in content_type:
                data_lines = [
                    line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")
                ]
                if not data_lines:
                    raise ValueError("MCP event stream contained no data")
                body = json.loads(data_lines[-1])
            else:
                body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise MCPClientError(f"MCP request failed: {exc}") from exc
        if body.get("error"):
            error = body["error"]
            raise MCPClientError(error.get("message", json.dumps(error)))
        if "result" not in body:
            raise MCPClientError("MCP response did not contain a result")
        return body["result"]

    def initialize(self):
        """Perform the MCP lifecycle handshake once per client session."""
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            payload = {
                "jsonrpc": "2.0",
                "id": next(self._request_ids),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "manavote-telegram", "version": "1.0"},
                },
            }
            self._post(payload)
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_result=False)
            self._initialized = True

    def request(self, method, params=None):
        self.initialize()
        payload = {"jsonrpc": "2.0", "id": next(self._request_ids), "method": method}
        if params is not None:
            payload["params"] = params
        return self._post(payload)

    def list_tools(self):
        return self.request("tools/list").get("tools", [])

    def call_tool(self, name, arguments):
        if not isinstance(arguments, dict):
            raise MCPClientError("MCP tool arguments must be a JSON object")
        return self.request("tools/call", {"name": name, "arguments": arguments})
