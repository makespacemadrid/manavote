"""Shared field validation for create-proposal/create-poll requests.

Framework-independent (no Flask, no JSON-RPC) so both REST (`api_routes.py`) and the
standalone MCP server (`mcp_server.py`, which must not import Flask) can share it.
"""


def parse_positive_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def normalize_poll_options(raw_options):
    if not isinstance(raw_options, list):
        return None
    options = [str(item).strip() for item in raw_options if str(item).strip()]
    if len(options) < 2 or len(options) > 12:
        return None
    if any(len(option) > 120 for option in options):
        return None
    return options
