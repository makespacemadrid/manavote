from datetime import datetime

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

TELEGRAM_LINK_SALT = "telegram-browser-link-v1"
TELEGRAM_LINK_MAX_AGE_SECONDS = 15 * 60


def create_browser_link_token(secret_key, telegram_username, telegram_user_id):
    """Create a short-lived signed token carrying a Telegram identity."""
    return URLSafeTimedSerializer(secret_key, salt=TELEGRAM_LINK_SALT).dumps(
        {
            "telegram_username": (telegram_username or "").strip(),
            "telegram_user_id": int(telegram_user_id),
        }
    )


def read_browser_link_token(secret_key, token, max_age=TELEGRAM_LINK_MAX_AGE_SECONDS):
    """Validate a browser-link token and return its Telegram identity."""
    try:
        payload = URLSafeTimedSerializer(secret_key, salt=TELEGRAM_LINK_SALT).loads(
            token, max_age=max_age
        )
        telegram_user_id = int(payload["telegram_user_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None
    return {
        "telegram_username": str(payload.get("telegram_username") or "").strip(),
        "telegram_user_id": telegram_user_id,
    }


def link_member_telegram(get_db, member_id, telegram_username, telegram_user_id):
    """Link a verified Telegram identity to the authenticated ManaVote member."""
    conn = get_db()
    try:
        occupied = conn.execute(
            "SELECT id FROM members WHERE telegram_user_id = ? AND id != ?",
            (int(telegram_user_id), int(member_id)),
        ).fetchone()
        if occupied:
            return False, "already_linked"
        normalized_username = (telegram_username or "").strip() or None
        cursor = conn.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ?, last_linked_at = ? WHERE id = ?",
            (normalized_username, int(telegram_user_id), datetime.now().isoformat(), int(member_id)),
        )
        if cursor.rowcount != 1:
            return False, "unknown_member"
        conn.commit()
        return True, "ok"
    finally:
        conn.close()


def unlink_member_telegram(get_db, member_id: int) -> None:
    conn = get_db()
    try:
        conn.execute(
            "UPDATE members SET telegram_username = NULL, telegram_user_id = NULL, last_unlinked_at = ? WHERE id = ?",
            (datetime.now().isoformat(), int(member_id)),
        )
        conn.commit()
    finally:
        conn.close()


def process_link_command(
    *,
    get_db,
    verify_and_migrate_password,
    telegram_username: str,
    telegram_user_id,
    command_text: str,
):
    command = (command_text or "").strip()
    parts = command.split(maxsplit=2)
    if len(parts) != 3:
        return False, "invalid_format", None
    app_username = parts[1].strip()
    password = parts[2]
    normalized_telegram_username = (telegram_username or "").strip() or None
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, password_hash FROM members WHERE lower(username) = lower(?)", (app_username,))
        member = c.fetchone()
        if not member:
            return False, "unknown_member", None
        ok, new_hash = verify_and_migrate_password(member["password_hash"], password)
        if not ok:
            return False, "invalid_credentials", None
        if new_hash:
            c.execute("UPDATE members SET password_hash = ? WHERE id = ?", (new_hash, member["id"]))

        c.execute("SELECT id FROM members WHERE telegram_user_id = ? AND id != ?", (telegram_user_id, member["id"]))
        linked = c.fetchone()
        if linked:
            return False, "already_linked", None

        c.execute(
            "UPDATE members SET telegram_username = ?, telegram_user_id = ?, last_linked_at = ? WHERE id = ?",
            (normalized_telegram_username, int(telegram_user_id), datetime.now().isoformat(), member["id"]),
        )
        conn.commit()
        return True, "ok", int(member["id"])
    finally:
        conn.close()
