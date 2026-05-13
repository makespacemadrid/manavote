def unlink_member_telegram(get_db, member_id: int) -> None:
    conn = get_db()
    try:
        conn.execute(
            "UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE id = ?",
            (int(member_id),),
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
    if not (telegram_username or "").strip():
        return False, "missing_public_username", None

    app_username = parts[1].strip()
    password = parts[2]
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
            "UPDATE members SET telegram_username = ?, telegram_user_id = ? WHERE id = ?",
            (telegram_username, int(telegram_user_id), member["id"]),
        )
        conn.commit()
        return True, "ok", int(member["id"])
    finally:
        conn.close()
