import json
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request, session

from app.extensions import csrf, limiter
from app.repositories.poll_repo import PollRepository
from app.repositories.member_repo import MemberRepository
from app.services import auth_service, poll_page_service, proposal_actions_service, proposal_page_service
from app.repositories.proposal_repo import ProposalRepository
from app.services import feedback_service, poll_service, voting_settings_service
from app.services.pagination_service import REASON_MESSAGES, parse_limit_offset
from app.services.user_statistics import user_statistics_rows
from app.services.voting_settings_service import VALID_VOTE_MODES
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


@api_bp.route("/api/feedback", methods=["POST"], endpoint="api_create_feedback")
@csrf.exempt
def api_create_feedback():
    member_id = session.get("member_id")
    if not member_id:
        return api_error("authentication_required", "Login required", 401)
    data, json_error = require_json_body()
    if json_error:
        return json_error
    conn = legacy.get_db()
    try:
        feedback_id = feedback_service.submit_feedback(
            conn,
            member_id=member_id,
            source="web",
            category=data.get("category"),
            message=data.get("message"),
            section=data.get("section"),
            logger=current_app.logger,
        )
    except feedback_service.FeedbackValidationError as exc:
        conn.close()
        return api_error(exc.code, str(exc), 400 if exc.code != "member_not_found" else 404)
    conn.close()
    return jsonify({"success": True, "feedback_id": feedback_id}), 201


@api_bp.route("/api/feedback", methods=["GET"], endpoint="api_list_feedback")
def api_list_feedback():
    if not session.get("member_id"):
        return api_error("authentication_required", "Login required", 401)
    if not session.get("is_admin"):
        return api_error("admin_required", "Admin access required", 403)
    limit, offset, reason = parse_limit_offset(request.args.get("limit"), request.args.get("offset"), 50, 100)
    if reason:
        return api_error(reason, REASON_MESSAGES[reason].format(max_limit=100), 400)
    conn = legacy.get_db()
    try:
        items = feedback_service.list_feedback(
            conn, status=request.args.get("status"), category=request.args.get("category"), limit=limit, offset=offset
        )
    except feedback_service.FeedbackValidationError as exc:
        conn.close()
        return api_error(exc.code, str(exc), 400)
    conn.close()
    return jsonify({"feedback": items, "limit": limit, "offset": offset})


@api_bp.route("/api/feedback/<int:feedback_id>", methods=["PATCH"], endpoint="api_update_feedback")
@csrf.exempt
def api_update_feedback(feedback_id):
    if not session.get("member_id"):
        return api_error("authentication_required", "Login required", 401)
    if not session.get("is_admin"):
        return api_error("admin_required", "Admin access required", 403)
    data, json_error = require_json_body()
    if json_error:
        return json_error
    conn = legacy.get_db()
    try:
        feedback_service.update_feedback_status(
            conn, feedback_id=feedback_id, status=str(data.get("status") or ""),
            resolved_by=session["member_id"], logger=current_app.logger,
        )
    except feedback_service.FeedbackValidationError as exc:
        conn.close()
        return api_error(exc.code, str(exc), 404 if exc.code == "feedback_not_found" else 400)
    conn.close()
    return jsonify({"success": True, "feedback_id": feedback_id, "status": data["status"]})


def _parse_optional_bool(value):
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

    conn = legacy.get_db()
    try:
        member_id = auth_service.register_member(conn, username, password, is_admin)
        if member_id is None:
            return api_error("username_exists", "Username already exists", 409)
        return jsonify({"success": True, "message": f"User {username} created", "member_id": member_id}), 201
    except sqlite3.Error:
        return api_error("register_failed", "Failed to create user", 500)
    finally:
        conn.close()


@api_bp.route("/api/proposals", methods=["POST"], endpoint="api_create_proposal")
@csrf.exempt
def api_create_proposal():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    data, json_error = require_json_body()
    if json_error:
        return json_error

    title = str(data.get("title") or "").strip()
    description = data.get("description", "")
    amount = data.get("amount")
    url = data.get("url", "")
    basic_supplies_flag = _parse_optional_bool(data.get("basic_supplies", False))
    created_by = data.get("created_by")

    if not title or amount is None:
        return api_error("title_amount_required", "title and amount are required", 400)
    amount = parse_positive_amount(amount)
    if amount is None:
        return api_error("amount_must_be_positive", "amount must be positive", 400)
    if not created_by:
        return api_error("created_by_required", "created_by is required", 400)
    if basic_supplies_flag is None:
        return api_error("invalid_basic_supplies", "basic_supplies must be boolean", 400)
    basic_supplies = 1 if basic_supplies_flag else 0

    conn = legacy.get_db()
    if MemberRepository(conn).get_by_id(created_by) is None:
        conn.close()
        return api_error("creator_member_not_found", "Creator member not found", 404)

    try:
        proposal_id = ProposalRepository(conn).create(title, description, amount, url, created_by, basic_supplies)
        conn.close()
        return jsonify({"success": True, "message": "Proposal created", "proposal_id": proposal_id}), 201
    except sqlite3.Error:
        conn.close()
        return api_error("proposal_create_failed", "Failed to create proposal", 500)


@api_bp.route("/api/proposals", methods=["GET"], endpoint="api_list_proposals")
@csrf.exempt
def api_list_proposals():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    status = (request.args.get("status") or "").strip().lower()
    age = (request.args.get("age") or "").strip().lower()
    limit, offset, pagination_error = parse_pagination_params(default_limit=50, max_limit=200)
    if pagination_error:
        return pagination_error
    filter_error = proposal_page_service.validate_api_filters(status, age)
    if filter_error:
        return api_error(*filter_error, 400)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).replace(tzinfo=None).isoformat(sep=" ")
    conn = legacy.get_db()
    try:
        rows = ProposalRepository(conn).list_for_api(status=status, age=age, cutoff=cutoff, limit=limit, offset=offset)
    finally:
        conn.close()

    return jsonify({"success": True, "count": len(rows), "limit": limit, "offset": offset, "proposals": [dict(r) for r in rows]})


@api_bp.route("/api/proposals/<int:proposal_id>", methods=["GET"], endpoint="api_get_proposal")
@csrf.exempt
def api_get_proposal(proposal_id):
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    conn = legacy.get_db()
    row = ProposalRepository(conn).api_details(proposal_id)
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
    try:
        proposal = proposal_actions_service.get_proposal_for_api_edit(conn, proposal_id)
    except proposal_actions_service.ProposalActionError as exc:
        conn.close()
        if exc.code == "proposal_not_found":
            return api_error("proposal_not_found", "Proposal not found", 404)
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
        proposal_actions_service.update_api_proposal(
            conn, proposal_id=proposal_id, title=title, description=description,
            amount=amount, url=url, basic_supplies=basic_supplies,
        )
        conn.close()
        return jsonify({"success": True, "message": "Proposal updated", "proposal_id": proposal_id})
    except sqlite3.Error as exc:
        legacy.app.logger.warning(
            "api_request_failure reason_code=proposal_update_failed proposal_id=%s error=%s",
            proposal_id,
            exc,
        )
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
    rows = MemberRepository(conn).list_telegram_links(include_unlinked, limit, offset)
    conn.close()

    return jsonify({"success": True, "count": len(rows), "limit": limit, "offset": offset, "members": [dict(r) for r in rows]})


@api_bp.route("/api/members/statistics", methods=["GET"], endpoint="api_list_user_statistics")
@csrf.exempt
def api_list_user_statistics():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error

    limit, offset, pagination_error = parse_pagination_params(default_limit=100, max_limit=500)
    if pagination_error:
        return pagination_error

    include_email_value = (request.args.get("include_email") or "false").strip().lower()
    if include_email_value not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        return api_error("invalid_include_email", "include_email must be boolean", 400)
    include_email = include_email_value in {"1", "true", "yes", "on"}

    conn = legacy.get_db()
    try:
        rows, total = MemberRepository(conn).statistics(limit, offset)
    finally:
        conn.close()

    return jsonify(
        {
            "success": True,
            "count": len(rows),
            "total": total,
            "limit": limit,
            "offset": offset,
            "users": user_statistics_rows(rows, include_email=include_email),
        }
    )


@api_bp.route("/api/settings/voting", methods=["GET"], endpoint="api_get_voting_settings")
@csrf.exempt
def api_get_voting_settings():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    return jsonify(
        {
            "success": True,
            "settings": {
                "poll_vote_mode": legacy.get_poll_vote_mode(),
                "proposal_vote_mode": legacy.get_proposal_vote_mode(),
                "telegram_require_linked_vote": legacy.require_linked_telegram_for_votes(),
            },
        }
    )


@api_bp.route("/api/settings/voting", methods=["PUT", "PATCH"], endpoint="api_update_voting_settings")
@csrf.exempt
def api_update_voting_settings():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    data, json_error = require_json_body()
    if json_error:
        return json_error

    poll_vote_mode = data.get("poll_vote_mode")
    proposal_vote_mode = data.get("proposal_vote_mode")
    linked_vote_policy = data.get("telegram_require_linked_vote")

    if poll_vote_mode is None and proposal_vote_mode is None and linked_vote_policy is None:
        return api_error("no_changes_provided", "at least one voting setting must be provided", 400)
    if poll_vote_mode is not None and poll_vote_mode not in VALID_VOTE_MODES:
        return api_error("invalid_poll_vote_mode", "poll_vote_mode must be one of: both, web_only, telegram_only", 400)
    if proposal_vote_mode is not None and proposal_vote_mode not in VALID_VOTE_MODES:
        return api_error("invalid_proposal_vote_mode", "proposal_vote_mode must be one of: both, web_only, telegram_only", 400)

    linked_vote_policy_bool = _parse_optional_bool(linked_vote_policy)
    if linked_vote_policy is not None and linked_vote_policy_bool is None:
        return api_error("invalid_telegram_require_linked_vote", "telegram_require_linked_vote must be a boolean", 400)

    conn = legacy.get_db()
    try:
        voting_settings_service.apply_voting_settings(
            conn,
            poll_vote_mode=poll_vote_mode,
            proposal_vote_mode=proposal_vote_mode,
            telegram_require_linked_vote=linked_vote_policy_bool,
        )
    finally:
        conn.close()

    return jsonify(
        {
            "success": True,
            "settings": {
                "poll_vote_mode": legacy.get_poll_vote_mode(),
                "proposal_vote_mode": legacy.get_proposal_vote_mode(),
                "telegram_require_linked_vote": legacy.require_linked_telegram_for_votes(),
            },
        }
    )


@api_bp.route("/api/polls", methods=["GET"], endpoint="api_list_polls")
@csrf.exempt
def api_list_polls():
    auth_error = require_api_key(legacy.ADMIN_API_KEY)
    if auth_error:
        return auth_error
    limit, offset, pagination_error = parse_pagination_params(default_limit=100, max_limit=200)
    if pagination_error:
        return pagination_error

    conn = legacy.get_db()
    try:
        polls = poll_page_service.list_api_polls(conn, limit, offset)
    finally:
        conn.close()
    return jsonify({"success": True, "count": len(polls), "limit": limit, "offset": offset, "polls": polls})


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
    allow_multiple = _parse_optional_bool(data.get("allow_multiple"))
    if allow_multiple is None and "allow_multiple" in data:
        return api_error("invalid_allow_multiple", "allow_multiple must be a boolean", 400)
    allow_multiple = bool(allow_multiple)
    if len(question) < 5 or len(question) > 200:
        return api_error("invalid_poll_question", "question must be between 5 and 200 characters", 400)
    if options is None:
        return api_error(
            "invalid_poll_options",
            "options must be an array with 2..12 non-empty items (max 120 chars each)",
            400,
        )
    if not created_by:
        return api_error("created_by_required", "created_by is required", 400)

    conn = legacy.get_db()
    if MemberRepository(conn).get_by_id(created_by) is None:
        conn.close()
        return api_error("creator_member_not_found", "Creator member not found", 404)
    try:
        poll_id = PollRepository(conn).create(question, options, created_by, allow_multiple)
    except sqlite3.Error:
        return api_error("poll_create_failed", "Failed to create poll", 500)
    finally:
        conn.close()
    legacy.send_telegram_message(
        poll_service.build_poll_announcement_message(question, options, allow_multiple=allow_multiple),
        poll_id,
        options,
    )
    return jsonify({"success": True, "message": "Poll created", "poll_id": poll_id}), 201
