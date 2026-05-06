"""Thin startup wrapper for the ManaVote application."""

import logging
import os
import threading

from app import app


def _start_mcp_if_enabled():
    enabled = os.getenv("MCP_SERVER_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return

    from app.mcp_server import start_tcp_server

    host = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_SERVER_PORT", "8765"))
    t = threading.Thread(target=start_tcp_server, kwargs={"host": host, "port": port}, daemon=True)
    t.start()
    logging.getLogger(__name__).info("Started MCP server thread on %s:%s", host, port)


if __name__ == "__main__":
    _start_mcp_if_enabled()
    app.run(host="0.0.0.0", port=5000)
