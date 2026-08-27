from app.services import pagination_service


def test_parse_limit_offset_defaults_when_absent():
    limit, offset, reason_code = pagination_service.parse_limit_offset(None, None, default_limit=20, max_limit=200)
    assert (limit, offset, reason_code) == (20, 0, None)


def test_parse_limit_offset_honors_provided_values():
    limit, offset, reason_code = pagination_service.parse_limit_offset("5", "10", default_limit=20, max_limit=200)
    assert (limit, offset, reason_code) == (5, 10, None)


def test_parse_limit_offset_rejects_non_integer_limit():
    limit, offset, reason_code = pagination_service.parse_limit_offset("abc", None, default_limit=20, max_limit=200)
    assert (limit, offset, reason_code) == (None, None, "invalid_limit")


def test_parse_limit_offset_rejects_non_integer_offset():
    limit, offset, reason_code = pagination_service.parse_limit_offset(None, "abc", default_limit=20, max_limit=200)
    assert (limit, offset, reason_code) == (None, None, "invalid_offset")


def test_parse_limit_offset_rejects_out_of_range_limit():
    _, _, low = pagination_service.parse_limit_offset(0, None, default_limit=20, max_limit=200)
    _, _, high = pagination_service.parse_limit_offset(201, None, default_limit=20, max_limit=200)
    assert low == high == "limit_out_of_range"


def test_parse_limit_offset_rejects_negative_offset():
    limit, offset, reason_code = pagination_service.parse_limit_offset(None, -1, default_limit=20, max_limit=200)
    assert (limit, offset, reason_code) == (None, None, "offset_out_of_range")


def test_reason_messages_cover_every_reason_code():
    for reason_code in ("invalid_limit", "invalid_offset", "limit_out_of_range", "offset_out_of_range"):
        assert reason_code in pagination_service.REASON_MESSAGES
    assert "{max_limit}" in pagination_service.REASON_MESSAGES["limit_out_of_range"]
