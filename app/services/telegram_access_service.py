"""Database-backed access control for Telegram assistant users."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class TelegramPrincipal:
    member_id: int
    telegram_user_id: int
    is_admin: bool


def load_telegram_principals(get_db: Callable) -> dict[int, TelegramPrincipal]:
    """Return the current Telegram-ID allowlist, keyed by Telegram user ID.

    The database remains the sole source of truth: linking/unlinking a member is
    reflected on the next message without restarting the application.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT id, telegram_user_id, is_admin
            FROM members
            WHERE telegram_user_id IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()

    return {
        int(row["telegram_user_id"]): TelegramPrincipal(
            member_id=int(row["id"]),
            telegram_user_id=int(row["telegram_user_id"]),
            is_admin=bool(row["is_admin"]),
        )
        for row in rows
    }


def get_telegram_principal(get_db: Callable, telegram_user_id) -> TelegramPrincipal | None:
    """Resolve a Telegram sender against the live database allowlist."""
    try:
        normalized_id = int(telegram_user_id)
    except (TypeError, ValueError):
        return None
    conn = get_db()
    try:
        row = conn.execute(
            """
            SELECT id, telegram_user_id, is_admin
            FROM members
            WHERE telegram_user_id = ?
            LIMIT 1
            """,
            (normalized_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return TelegramPrincipal(
        member_id=int(row["id"]),
        telegram_user_id=int(row["telegram_user_id"]),
        is_admin=bool(row["is_admin"]),
    )
