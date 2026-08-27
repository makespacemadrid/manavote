import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_app_timezone(get_db):
    """Get configured timezone from settings; fallback to Europe/Madrid."""
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'timezone'")
        row = c.fetchone()
        tz_name = row["value"] if row else "Europe/Madrid"
        return ZoneInfo(tz_name)
    except (sqlite3.Error, KeyError, IndexError, TypeError, ZoneInfoNotFoundError):
        return ZoneInfo("Europe/Madrid")
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass


def format_datetime(dt_str, get_db, fmt="%Y-%m-%d %H:%M:%S"):
    """Convert datetime string to configured timezone and format it."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        tz = get_app_timezone(get_db)
        dt_local = dt.astimezone(tz)
        return dt_local.strftime(fmt)
    except (ValueError, TypeError):
        return dt_str


def truncate_username(username):
    if not username:
        return "unknown"
    if "@" in username:
        return username.split("@")[0]
    return username


def detect_image_type(filepath: str) -> str | None:
    with open(filepath, "rb") as f:
        header = f.read(12)

    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    return None
