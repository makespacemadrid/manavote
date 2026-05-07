import json

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from app.extensions import csrf, limiter
from app.web.routes import main_routes as legacy
from app.web.routes.helpers.api_helpers import (
    normalize_poll_options,
    parse_pagination_params,
    parse_positive_amount,
    require_api_key,
    require_json_body,
    api_error,
)

api_bp = Blueprint("api", __name__)



@api_bp.route("/api/register", methods=["POST"], endpoint="api_register")
@limiter.limit("10 per minute")
@csrf.exempt
def api_register():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error

    data, json_error = require_json_body()
    if json_error:
        return json_error

    username = data.get("username")
    password = data.get("password")
    is_admin = data.get("is_admin", False)

    if not username or not password:
        return api_error("username_password_required", "username and password are required", 400)

    password_hash = generate_password_hash(password)

    conn = legacy.get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM members WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        return api_error("username_exists", "Username already exists", 409)

    try:
        c.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, password_hash, 1 if is_admin else 0),
        )
        conn.commit()
        member_id = c.lastrowid
        conn.close()
        return jsonify({"success": True, "message": f"User {username} created", "member_id": member_id}), 201
    except Exception as e:
        conn.close()
        return api_error("register_failed", "Failed to create user", 500)


@api_bp.route("/api/proposals", methods=["POST"], endpoint="api_create_proposal")
@csrf.exempt
def api_create_proposal():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    data, json_error = require_json_body()
    if json_error:
        return json_error

    title = data.get("title")
    description = data.get("description", "")
    amount = data.get("amount")
    url = data.get("url", "")
    basic_supplies = 1 if data.get("basic_supplies", False) else 0
    created_by = data.get("created_by")

    if not title or amount is None:
        return api_error("title_amount_required", "title and amount are required", 400)
    amount = parse_positive_amount(amount)
    if amount is None:
        return api_error("amount_must_be_positive", "amount must be positive", 400)
    if not created_by:
        return api_error("created_by_required", "created_by is required", 400)

    conn = legacy.get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM members WHERE id = ?", (created_by,))
    if not c.fetchone():
        conn.close()
        return api_error("creator_not_found", "Creator member not found", 404)

    try:
        c.execute(
            "INSERT INTO proposals (title, description, amount, url, created_by, basic_supplies) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, amount, url, created_by, basic_supplies),
        )
        conn.commit()
        proposal_id = c.lastrowid
        if basic_supplies and amount > 20.0:
            c.execute("UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,))
            c.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (proposal_id, created_by, "Auto-removed basic supplies flag: amount over €20"),
            )
            conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Proposal created", "proposal_id": proposal_id}), 201
    except Exception as e:
        conn.close()
        return api_error("proposal_create_failed", "Failed to create proposal", 500)


@api_bp.route("/api/proposals", methods=["GET"], endpoint="api_list_proposals")
@csrf.exempt
def api_list_proposals():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    status = (request.args.get("status") or "").strip().lower()
    valid_statuses = {"active", "accepted", "rejected", "purchased"}
    limit, offset, pagination_error = parse_pagination_params(default_limit=50, max_limit=200)
    if pagination_error:
        return pagination_error

    params = []
    query = """
        SELECT p.id, p.title, p.description, p.amount, p.url, p.created_by, p.status, p.created_at, p.basic_supplies,
               COALESCE(SUM(CASE WHEN v.vote = 'yes' THEN 1 ELSE 0 END), 0) AS yes_votes,
               COALESCE(SUM(CASE WHEN v.vote = 'no' THEN 1 ELSE 0 END), 0) AS no_votes
        FROM proposals p
        LEFT JOIN votes v ON v.proposal_id = p.id
    """
    if status:
        if status not in valid_statuses:
            return api_error("invalid_status_filter", "invalid status filter", 400)
        query += " WHERE p.status = ?"
        params.append(status)

    query += " GROUP BY p.id ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = legacy.get_db()
    c = conn.cursor()
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    return jsonify({"success": True, "count": len(rows), "limit": limit, "offset": offset, "proposals": [dict(r) for r in rows]})


@api_bp.route("/api/proposals/<int:proposal_id>", methods=["GET"], endpoint="api_get_proposal")
@csrf.exempt
def api_get_proposal(proposal_id):
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    conn = legacy.get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, title, description, amount, url, created_by, status, created_at, basic_supplies FROM proposals WHERE id = ?",
        (proposal_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return api_error("proposal_not_found", "Proposal not found", 404)
    return jsonify({"success": True, "proposal": dict(row)})


@api_bp.route("/api/proposals/<int:proposal_id>", methods=["PUT", "PATCH"], endpoint="api_edit_proposal")
@csrf.exempt
def api_edit_proposal(proposal_id):
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error

    conn = legacy.get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()
    if not proposal:
        conn.close()
        return api_error("proposal_not_found", "Proposal not found", 404)
    if proposal["status"] != "active":
        conn.close()
        return api_error("proposal_already_processed", "Cannot edit processed proposals", 400)

    data, json_error = require_json_body()
    if json_error:
        conn.close()
        return json_error

    title = data.get("title", proposal["title"])
    description = data.get("description", proposal["description"])
    amount = data.get("amount", proposal["amount"])
    url = data.get("url", proposal["url"])
    basic_supplies = 1 if data.get("basic_supplies", proposal["basic_supplies"]) else 0

    amount = parse_positive_amount(amount)
    if amount is None:
        conn.close()
        return api_error("amount_must_be_positive", "amount must be positive", 400)

    try:
        c.execute(
            "UPDATE proposals SET title = ?, description = ?, amount = ?, url = ?, basic_supplies = ? WHERE id = ?",
            (title, description, amount, url, basic_supplies, proposal_id),
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Proposal updated", "proposal_id": proposal_id})
    except Exception as e:
        conn.close()
        return api_error("proposal_update_failed", "Failed to update proposal", 500)


@api_bp.route("/api/members/telegram", methods=["GET"], endpoint="api_list_member_telegram_links")
@csrf.exempt
def api_list_member_telegram_links():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error

    include_unlinked = (request.args.get("include_unlinked") or "false").strip().lower() in {"1", "true", "yes", "on"}
    limit, offset, pagination_error = parse_pagination_params(default_limit=100, max_limit=500)
    if pagination_error:
        return pagination_error

    conn = legacy.get_db()
    c = conn.cursor()
    if include_unlinked:
        c.execute(
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
        c.execute(
            """
            SELECT id, username, telegram_username, telegram_user_id, 1 AS linked
            FROM members
            WHERE telegram_username IS NOT NULL AND telegram_username != '' AND telegram_user_id IS NOT NULL
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    rows = c.fetchall()
    conn.close()

    return jsonify({"success": True, "count": len(rows), "limit": limit, "offset": offset, "members": [dict(r) for r in rows]})


@api_bp.route("/api/polls", methods=["GET"], endpoint="api_list_polls")
@csrf.exempt
def api_list_polls():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error

    conn = legacy.get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT p.id, p.question, p.options_json, p.status, p.created_at, p.created_by,
               (SELECT COUNT(*) FROM poll_votes pv WHERE pv.poll_id = p.id) AS total_votes
        FROM polls p
        ORDER BY p.created_at DESC
        LIMIT 100
        """
    )
    rows = c.fetchall()
    conn.close()
    polls = []
    for row in rows:
        poll = dict(row)
        try:
            poll["options"] = json.loads(poll.pop("options_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            poll["options"] = []
        polls.append(poll)
    return jsonify({"success": True, "polls": polls})


@api_bp.route("/api/polls", methods=["POST"], endpoint="api_create_poll")
@csrf.exempt
def api_create_poll():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    data, json_error = require_json_body()
    if json_error:
        return json_error

    question = str(data.get("question", "")).strip()
    options = normalize_poll_options(data.get("options"))
    created_by = data.get("created_by")
    if len(question) < 5 or len(question) > 200:
        return jsonify({"error": "question must be between 5 and 200 characters"}), 400
    if options is None:
        return jsonify({"error": "options must be an array with 2..12 non-empty items (max 120 chars each)"}), 400
    if not created_by:
        return api_error("created_by_required", "created_by is required", 400)

    conn = legacy.get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM members WHERE id = ?", (created_by,))
    if not c.fetchone():
        conn.close()
        return api_error("creator_not_found", "Creator member not found", 404)
    c.execute(
        "INSERT INTO polls (question, options_json, created_by, status) VALUES (?, ?, ?, 'open')",
        (question, json.dumps(options), created_by),
    )
    conn.commit()
    poll_id = c.lastrowid
    conn.close()
    return jsonify({"success": True, "message": "Poll created", "poll_id": poll_id}), 201
