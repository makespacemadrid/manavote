import pytest

from app.integrations.mcp_client import MCPClient, MCPClientError


class Response:
    def __init__(self, body):
        self.body = body
        self.headers = {}
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def test_list_tools_authenticates_with_header(monkeypatch):
    captured = []

    def post(url, **kwargs):
        captured.append({"url": url, **kwargs})
        method = kwargs["json"]["method"]
        if method == "initialize":
            return Response({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"tools": {}}}})
        if method == "notifications/initialized":
            return Response({})
        return Response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "current_budget"}]}})

    session = type("Session", (), {"post": staticmethod(post)})()
    assert MCPClient("http://mcp/mcp", "secret", session=session).list_tools() == [{"name": "current_budget"}]
    assert captured[0]["headers"]["X-Api-Key"] == "secret"
    assert captured[0]["headers"]["Accept"] == "application/json, text/event-stream"
    assert [request["json"]["method"] for request in captured] == [
        "initialize", "notifications/initialized", "tools/list"
    ]


def test_call_tool_surfaces_json_rpc_error(monkeypatch):
    responses = iter([
        Response({"result": {"capabilities": {}}}),
        Response({}),
        Response({"error": {"code": -32602, "message": "bad arguments"}}),
    ])
    session = type(
        "Session",
        (),
        {"post": staticmethod(lambda *_args, **_kwargs: next(responses))},
    )()
    with pytest.raises(MCPClientError, match="bad arguments"):
        MCPClient("http://mcp/mcp", "secret", session=session).call_tool("thing", {})


def test_call_tool_rejects_non_object_arguments_without_network_call():
    with pytest.raises(MCPClientError, match="JSON object"):
        MCPClient("http://mcp/mcp", "secret").call_tool("thing", [])


def test_server_session_id_is_reused_after_initialize():
    requests_seen = []

    def post(_url, **kwargs):
        requests_seen.append(kwargs)
        response = Response({"result": {"tools": []}})
        if kwargs["json"]["method"] == "initialize":
            response.headers["Mcp-Session-Id"] = "session-123"
        return response

    session = type("Session", (), {"post": staticmethod(post)})()
    MCPClient("http://mcp/mcp", "secret", session=session).list_tools()
    assert "Mcp-Session-Id" not in requests_seen[0]["headers"]
    assert requests_seen[1]["headers"]["Mcp-Session-Id"] == "session-123"
    assert requests_seen[2]["headers"]["Mcp-Session-Id"] == "session-123"


def test_streamable_http_sse_response_is_parsed():
    responses = []
    initialize = Response({"result": {"capabilities": {}}})
    notification = Response({})
    tools = Response(None)
    tools.headers["Content-Type"] = "text/event-stream; charset=utf-8"
    tools.text = 'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n\n'
    responses.extend([initialize, notification, tools])
    session = type("Session", (), {"post": staticmethod(lambda *_args, **_kwargs: responses.pop(0))})()
    assert MCPClient("http://mcp/mcp", "secret", session=session).list_tools() == []
