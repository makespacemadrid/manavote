from flask import Flask

from app.web.routes.helpers.api_helpers import (
    api_error,
    normalize_poll_options,
    parse_pagination_params,
    parse_positive_amount,
    require_api_key,
    require_json_body,
)


app = Flask(__name__)


def test_require_api_key_accepts_correct_header():
    with app.test_request_context(headers={"X-Admin-Key": "k"}):
        assert require_api_key("k") is None


def test_require_api_key_rejects_missing_or_wrong_header():
    with app.test_request_context(headers={}):
        payload, status = require_api_key("k")
        assert status == 401
        err = payload.get_json()["error"]
        assert err["code"] == "unauthorized"
        assert err["message"] == "Unauthorized"


def test_require_json_body_validation():
    with app.test_request_context(data="x", content_type="text/plain"):
        _, err = require_json_body()
        assert err[1] == 415

    with app.test_request_context(json={"ok": True}):
        data, err = require_json_body()
        assert err is None
        assert data["ok"] is True


def test_parse_helpers():
    assert parse_positive_amount("3.5") == 3.5
    assert parse_positive_amount("0") is None
    assert normalize_poll_options([" a ", "b"]) == ["a", "b"]
    assert normalize_poll_options(["only-one"]) is None


def test_parse_pagination_params():
    with app.test_request_context(query_string={"limit": "10", "offset": "2"}):
        limit, offset, err = parse_pagination_params()
        assert err is None
        assert (limit, offset) == (10, 2)

    with app.test_request_context(query_string={"limit": "999"}):
        _, _, err = parse_pagination_params(max_limit=200)
        assert err[1] == 400
        payload = err[0].get_json()["error"]
        assert payload["code"] == "limit_out_of_range"


def test_api_error_envelope_shape():
    with app.app_context():
        payload, status = api_error("example_code", "Example message", 418)
        assert status == 418
        assert payload.get_json() == {"error": {"code": "example_code", "message": "Example message"}}


def test_parse_pagination_params_invalid_offset_shape():
    with app.test_request_context(query_string={"offset": "-3"}):
        _, _, err = parse_pagination_params(max_limit=200)
        assert err[1] == 400
        payload = err[0].get_json()["error"]
        assert payload["code"] == "offset_out_of_range"
