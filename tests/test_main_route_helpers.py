from app.web.routes.helpers.main_helpers import (
    detect_image_type,
    format_datetime,
    get_app_timezone,
    truncate_username,
)


class _DummyCursor:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        return self.row


class _DummyConn:
    def __init__(self, row):
        self._cursor = _DummyCursor(row)

    def cursor(self):
        return self._cursor

    def close(self):
        return None


def test_truncate_username():
    assert truncate_username(None) == "unknown"
    assert truncate_username("alice@example.org") == "alice"
    assert truncate_username("bob") == "bob"


def test_get_app_timezone_uses_setting_row():
    tz = get_app_timezone(lambda: _DummyConn({"value": "UTC"}))
    assert str(tz) == "UTC"


def test_format_datetime_converts_to_target_timezone():
    formatted = format_datetime(
        "2026-05-09T12:00:00+00:00",
        lambda: _DummyConn({"value": "Europe/Madrid"}),
        "%Y-%m-%d %H:%M",
    )
    assert formatted == "2026-05-09 14:00"


def test_detect_image_type_png(tmp_path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 10)
    assert detect_image_type(str(image_path)) == "png"
