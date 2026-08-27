"""Shared limit/offset parsing and validation for list endpoints.

Transport-agnostic: takes the raw (unparsed) limit/offset values and returns normalized
integers or a stable reason code, so each transport applies its own error envelope around
the same validation rule -- REST wraps a reason code in
`{"error": {"code": ..., "message": ...}}`, MCP wraps it in a JSON-RPC -32602 error. This is
also the boundary that stops the two transports' bounds/type checks from silently drifting
apart, which is exactly how the `GET /api/polls` pagination gap happened.
"""

REASON_MESSAGES = {
    "invalid_limit": "limit must be an integer",
    "invalid_offset": "offset must be an integer",
    "limit_out_of_range": "limit must be between 1 and {max_limit}",
    "offset_out_of_range": "offset must be >= 0",
}


def parse_limit_offset(raw_limit, raw_offset, default_limit, max_limit):
    """Returns (limit, offset, reason_code).

    `raw_limit`/`raw_offset` should be the value as provided by the caller, or None when
    not provided (the default_limit/0 is used in that case). reason_code is None on
    success, else one of 'invalid_limit', 'invalid_offset', 'limit_out_of_range',
    'offset_out_of_range' -- see REASON_MESSAGES for a human-readable message per code.
    """
    try:
        limit = int(raw_limit) if raw_limit is not None else default_limit
    except (TypeError, ValueError):
        return None, None, "invalid_limit"
    try:
        offset = int(raw_offset) if raw_offset is not None else 0
    except (TypeError, ValueError):
        return None, None, "invalid_offset"
    if limit < 1 or limit > max_limit:
        return None, None, "limit_out_of_range"
    if offset < 0:
        return None, None, "offset_out_of_range"
    return limit, offset, None
