from flask import jsonify, request


def api_error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def require_api_key(admin_api_key: str):
    if not admin_api_key:
        return api_error("api_not_configured", "API not configured", 503)
    provided_key = request.headers.get("X-Admin-Key", "")
    if provided_key != admin_api_key:
        return api_error("unauthorized", "Unauthorized", 401)
    return None


def require_json_body():
    if not request.is_json:
        return None, api_error("unsupported_media_type", "Content-Type must be application/json", 415)
    data = request.get_json(silent=True)
    if not data:
        return None, api_error("json_body_required", "JSON body required", 400)
    return data, None


def parse_positive_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def parse_pagination_params(default_limit=50, max_limit=200):
    try:
        limit = int(request.args.get("limit", default_limit))
    except (TypeError, ValueError):
        return None, None, api_error("invalid_limit", "limit must be an integer", 400)
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return None, None, api_error("invalid_offset", "offset must be an integer", 400)
    if limit < 1 or limit > max_limit:
        return None, None, api_error("limit_out_of_range", f"limit must be between 1 and {max_limit}", 400)
    if offset < 0:
        return None, None, api_error("offset_out_of_range", "offset must be >= 0", 400)
    return limit, offset, None


def normalize_poll_options(raw_options):
    if not isinstance(raw_options, list):
        return None
    options = [str(item).strip() for item in raw_options if str(item).strip()]
    if len(options) < 2 or len(options) > 12:
        return None
    if any(len(option) > 120 for option in options):
        return None
    return options
