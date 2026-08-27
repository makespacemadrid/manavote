import importlib.util
import json
import os
from pathlib import Path

import app as budget_app


os.environ["MCP_API_KEY"] = "test-mcp-key"
spec = importlib.util.spec_from_file_location("manavote_mcp_server", Path("app/mcp_server.py"))
mcp_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mcp_server)
mcp_server.DB_PATH = budget_app.DB_PATH


def _mcp_req(name, arguments=None, req_id=1):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"api_key": "test-mcp-key", "name": name, "arguments": arguments or {}},
    }


def _with_admin_api_key():
    from app.web.routes import main_routes

    old = main_routes.ADMIN_API_KEY
    main_routes.ADMIN_API_KEY = "test-key"
    return old


def test_voting_settings_invalid_poll_mode_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"poll_vote_mode": "invalid_mode"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(_mcp_req("update_voting_settings", {"poll_vote_mode": "invalid_mode"}, req_id=2))

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_poll_vote_mode"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_invalid_linked_flag_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"telegram_require_linked_vote": "maybe"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("update_voting_settings", {"telegram_require_linked_vote": "maybe"}, req_id=3)
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_telegram_require_linked_vote"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_invalid_proposal_mode_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"proposal_vote_mode": "invalid_mode"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(_mcp_req("update_voting_settings", {"proposal_vote_mode": "invalid_mode"}, req_id=31))

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_proposal_vote_mode"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_missing_fields_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={"unrelated": True},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(_mcp_req("update_voting_settings", {}, req_id=32))

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "no_changes_provided"
    assert mcp["error"]["code"] == -32602


def test_voting_settings_success_shape_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.patch(
            "/api/settings/voting",
            headers={"X-Admin-Key": "test-key"},
            json={
                "poll_vote_mode": "both",
                "proposal_vote_mode": "telegram_only",
                "telegram_require_linked_vote": True,
            },
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req(
            "update_voting_settings",
            {
                "poll_vote_mode": "both",
                "proposal_vote_mode": "telegram_only",
                "telegram_require_linked_vote": True,
            },
            req_id=4,
        )
    )
    mcp_payload = json.loads(mcp["result"]["content"][0]["text"])
    rest_payload = rest.get_json()["settings"]
    for key in ("poll_vote_mode", "proposal_vote_mode", "telegram_require_linked_vote"):
        assert key in rest_payload
        assert key in mcp_payload


def test_member_telegram_link_listing_shape_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    conn = budget_app.get_db()
    conn.execute("DELETE FROM members")
    conn.executemany(
        "INSERT INTO members (id, username, password_hash, is_admin, telegram_username, telegram_user_id) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "linked", "x", 0, "linked_tg", 7001),
            (2, "missing_username", "x", 0, "", 7002),
            (3, "missing_user_id", "x", 0, "only_name", None),
            (4, "unlinked", "x", 0, None, None),
        ],
    )
    conn.commit()
    conn.close()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/telegram?include_unlinked=true&limit=50&offset=0",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("list_member_telegram_links", {"include_unlinked": True, "limit": 50, "offset": 0}, req_id=5)
    )

    assert rest.status_code == 200
    rest_members = rest.get_json()["members"]
    mcp_members = json.loads(mcp["result"]["content"][0]["text"])["members"]
    assert len(rest_members) == len(mcp_members) == 4

    rest_view = {row["username"]: (row["linked"], row["link_state"]) for row in rest_members}
    mcp_view = {row["username"]: (row["linked"], row["link_state"]) for row in mcp_members}
    assert rest_view == mcp_view


def test_user_statistics_success_shape_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/statistics?limit=50&offset=0",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("list_user_statistics", {"limit": 50, "offset": 0}, req_id=7)
    )

    assert rest.status_code == 200
    rest_payload = rest.get_json()
    mcp_payload = json.loads(mcp["result"]["content"][0]["text"])
    assert rest_payload["count"] == mcp_payload["count"]
    assert rest_payload["total"] == mcp_payload["total"]
    assert rest_payload["users"] == mcp_payload["users"]
    assert all("email" not in user for user in rest_payload["users"])


def test_user_statistics_invalid_limit_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/statistics?limit=501",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("list_user_statistics", {"limit": 501}, req_id=8)
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "limit_out_of_range"
    assert mcp["error"]["code"] == -32602


def test_user_statistics_email_opt_in_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/statistics?include_email=true&limit=50",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key
    mcp = mcp_server.handle_request(
        _mcp_req("list_user_statistics", {"include_email": True, "limit": 50}, req_id=9)
    )
    rest_users = rest.get_json()["users"]
    mcp_users = json.loads(mcp["result"]["content"][0]["text"])["users"]
    assert rest_users == mcp_users
    assert all("email" in user for user in rest_users)


def test_user_statistics_invalid_email_flag_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/statistics?include_email=sometimes",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key
    mcp = mcp_server.handle_request(
        _mcp_req("list_user_statistics", {"include_email": "sometimes"}, req_id=10)
    )
    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_include_email"
    assert mcp["error"]["code"] == -32602


def test_member_telegram_link_listing_invalid_limit_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()

    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.get(
            "/api/members/telegram?limit=999",
            headers={"X-Admin-Key": "test-key"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("list_member_telegram_links", {"limit": 999}, req_id=6)
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "limit_out_of_range"
    assert mcp["error"]["code"] == -32602


def test_create_proposal_missing_fields_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/proposals",
            headers={"X-Admin-Key": "test-key"},
            json={"title": "Missing amount"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(_mcp_req("create_proposal", {"title": "Missing amount"}, req_id=7))

    assert rest.status_code == 400
    assert mcp["error"]["code"] == -32602


def test_create_proposal_non_positive_amount_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/proposals",
            headers={"X-Admin-Key": "test-key"},
            json={"title": "Free item", "amount": 0, "created_by": 1},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("create_proposal", {"title": "Free item", "amount": 0, "created_by": 1}, req_id=8)
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "amount_must_be_positive"
    assert mcp["error"]["code"] == -32602


def test_create_proposal_unknown_creator_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/proposals",
            headers={"X-Admin-Key": "test-key"},
            json={"title": "Orphan proposal", "amount": 10, "created_by": 999999},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req(
            "create_proposal",
            {"title": "Orphan proposal", "amount": 10, "created_by": 999999},
            req_id=9,
        )
    )

    assert rest.status_code == 404
    assert rest.get_json()["error"]["code"] == "creator_member_not_found"
    assert mcp["error"]["code"] == -32004


def test_create_proposal_non_positive_creator_id_is_not_found_not_invalid_params():
    """A non-positive but well-typed created_by should be classified the same way as an
    unknown member (not found), consistent with create_poll and the REST endpoint -
    not treated as a params-shape error."""
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/proposals",
            headers={"X-Admin-Key": "test-key"},
            json={"title": "Negative creator", "amount": 10, "created_by": -5},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("create_proposal", {"title": "Negative creator", "amount": 10, "created_by": -5}, req_id=10)
    )

    assert rest.status_code == 404
    assert rest.get_json()["error"]["code"] == "creator_member_not_found"
    assert mcp["error"]["code"] == -32004


def test_create_proposal_invalid_basic_supplies_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/proposals",
            headers={"X-Admin-Key": "test-key"},
            json={"title": "Odd flag", "amount": 10, "created_by": 1, "basic_supplies": "maybe"},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req(
            "create_proposal",
            {"title": "Odd flag", "amount": 10, "created_by": 1, "basic_supplies": "maybe"},
            req_id=11,
        )
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_basic_supplies"
    assert mcp["error"]["code"] == -32602


def test_create_proposal_success_shape_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/proposals",
            headers={"X-Admin-Key": "test-key"},
            json={"title": "REST-created widget", "amount": 12.5, "created_by": 1},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req(
            "create_proposal",
            {"title": "MCP-created widget", "amount": 12.5, "created_by": 1},
            req_id=12,
        )
    )

    assert rest.status_code == 201
    rest_payload = rest.get_json()
    assert rest_payload["success"] is True
    assert isinstance(rest_payload["proposal_id"], int)

    mcp_payload = json.loads(mcp["result"]["content"][0]["text"])
    assert mcp_payload["success"] is True
    assert isinstance(mcp_payload["proposal_id"], int)


def test_create_poll_question_bounds_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/polls",
            headers={"X-Admin-Key": "test-key"},
            json={"question": "no", "options": ["A", "B"], "created_by": 1},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req("create_poll", {"question": "no", "options": ["A", "B"], "created_by": 1}, req_id=13)
    )

    assert rest.status_code == 400
    assert rest.get_json()["error"]["code"] == "invalid_poll_question"
    assert mcp["error"]["code"] == -32602


def test_create_poll_option_bounds_rejected_by_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    too_few = {"question": "Valid question?", "options": ["A"], "created_by": 1}
    too_many = {
        "question": "Valid question?",
        "options": [str(i) for i in range(13)],
        "created_by": 1,
    }
    too_long_option = {
        "question": "Valid question?",
        "options": ["A" * 121, "B"],
        "created_by": 1,
    }

    old_key = _with_admin_api_key()
    try:
        for payload in (too_few, too_many, too_long_option):
            rest = client.post(
                "/api/polls",
                headers={"X-Admin-Key": "test-key"},
                json=payload,
            )
            assert rest.status_code == 400
            assert rest.get_json()["error"]["code"] == "invalid_poll_options"
    finally:
        main_routes.ADMIN_API_KEY = old_key

    for index, payload in enumerate((too_few, too_many, too_long_option)):
        mcp = mcp_server.handle_request(_mcp_req("create_poll", payload, req_id=14 + index))
        assert mcp["error"]["code"] == -32602


def test_create_poll_success_shape_matches_between_rest_and_mcp():
    budget_app.app.config["TESTING"] = True
    client = budget_app.app.test_client()
    from app.web.routes import main_routes

    old_key = _with_admin_api_key()
    try:
        rest = client.post(
            "/api/polls",
            headers={"X-Admin-Key": "test-key"},
            json={"question": "REST poll: pick one?", "options": ["A", "B"], "created_by": 1},
        )
    finally:
        main_routes.ADMIN_API_KEY = old_key

    mcp = mcp_server.handle_request(
        _mcp_req(
            "create_poll",
            {"question": "MCP poll: pick one?", "options": ["A", "B"], "created_by": 1},
            req_id=17,
        )
    )

    assert rest.status_code == 201
    rest_payload = rest.get_json()
    assert rest_payload["success"] is True
    assert isinstance(rest_payload["poll_id"], int)

    mcp_payload = json.loads(mcp["result"]["content"][0]["text"])
    assert mcp_payload["success"] is True
    assert isinstance(mcp_payload["poll_id"], int)
