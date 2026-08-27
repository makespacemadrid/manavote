from app.services import creation_validation_service


def test_parse_positive_amount_accepts_numeric_strings():
    assert creation_validation_service.parse_positive_amount("3.5") == 3.5


def test_parse_positive_amount_rejects_zero_and_negative():
    assert creation_validation_service.parse_positive_amount("0") is None
    assert creation_validation_service.parse_positive_amount(-5) is None


def test_parse_positive_amount_rejects_non_numeric():
    assert creation_validation_service.parse_positive_amount("abc") is None
    assert creation_validation_service.parse_positive_amount(None) is None


def test_normalize_poll_options_strips_and_drops_empty():
    assert creation_validation_service.normalize_poll_options([" a ", "b", "  "]) == ["a", "b"]


def test_normalize_poll_options_rejects_non_list():
    assert creation_validation_service.normalize_poll_options("a,b") is None


def test_normalize_poll_options_rejects_too_few_or_too_many():
    assert creation_validation_service.normalize_poll_options(["only-one"]) is None
    assert creation_validation_service.normalize_poll_options([str(i) for i in range(13)]) is None


def test_normalize_poll_options_rejects_overly_long_option():
    assert creation_validation_service.normalize_poll_options(["a" * 121, "b"]) is None
