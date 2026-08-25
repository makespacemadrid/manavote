from unittest.mock import patch

from app.web.routes import main_routes


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False
        self.query = None

    def execute(self, query):
        self.query = query
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


def test_linked_telegram_user_id_is_automatically_allowed(monkeypatch):
    conn = FakeConnection([{"telegram_user_id": 4242}])
    monkeypatch.setattr(main_routes, "get_db", lambda: conn)
    monkeypatch.setattr(main_routes, "TELEGRAM_MCP_ALLOWED_USER_IDS", "")

    with patch.object(main_routes, "run_telegram_mcp_command", return_value="ok") as run:
        result = main_routes.process_telegram_mcp_command(
            {"text": "/mcp tools", "telegram_user_id": 4242, "chat_type": "private"}
        )

    assert result == "ok"
    assert run.call_args.kwargs["allowed_user_ids"] == {"4242"}
    assert "telegram_user_id IS NOT NULL" in conn.query
    assert conn.closed is True


def test_configured_ids_are_added_to_linked_member_ids(monkeypatch):
    conn = FakeConnection([{"telegram_user_id": 4242}])
    monkeypatch.setattr(main_routes, "get_db", lambda: conn)
    monkeypatch.setattr(main_routes, "TELEGRAM_MCP_ALLOWED_USER_IDS", "7, 8")

    with patch.object(main_routes, "run_telegram_mcp_command", return_value="ok") as run:
        main_routes.process_telegram_mcp_command(
            {"text": "/mcp tools", "telegram_user_id": 7, "chat_type": "private"}
        )

    assert run.call_args.kwargs["allowed_user_ids"] == {"7", "8", "4242"}
