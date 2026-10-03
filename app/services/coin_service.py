"""Shared business rules for web, QR, MCP, and Telegram Coins actions."""

import logging
import secrets
import sqlite3

from app.repositories.coin_repo import CoinRepository

MAX_QUANTITY = 1000
VALID_ACTIONS = {"consume": -1, "replenish": 1}
logger = logging.getLogger(__name__)


class CoinValidationError(ValueError):
    pass


class CoinNotFoundError(LookupError):
    pass


def create_item(connection, *, name, pack_size):
    """Create a uniquely named active item category with a purchase shortcut size."""
    name = str(name or "").strip()
    if not name or len(name) > 100:
        raise CoinValidationError("Item name must be between 1 and 100 characters")
    if isinstance(pack_size, bool):
        raise CoinValidationError("Pack size must be a positive integer")
    try:
        pack_size = int(pack_size)
    except (TypeError, ValueError) as exc:
        raise CoinValidationError("Pack size must be a positive integer") from exc
    if pack_size < 1 or pack_size > MAX_QUANTITY:
        raise CoinValidationError(f"Pack size must be between 1 and {MAX_QUANTITY}")
    repo = CoinRepository(connection)
    if connection.execute(
        "SELECT 1 FROM coin_items WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone():
        raise CoinValidationError("An item with that name already exists")
    try:
        item_id = repo.insert_item(name, pack_size)
        connection.commit()
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise CoinValidationError("An item with that name already exists") from exc
    logger.info("coin_item_created item_id=%s name=%s pack_size=%s", item_id, name, pack_size)
    return {"item_id": int(item_id), "name": name, "pack_size": pack_size}


def update_item(connection, *, item_id, name, pack_size):
    """Update an active item's display name and default purchase amount."""
    try:
        item_id = int(item_id)
    except (TypeError, ValueError) as exc:
        raise CoinValidationError("Coin item is required") from exc
    name = str(name or "").strip()
    if not name or len(name) > 100:
        raise CoinValidationError("Item name must be between 1 and 100 characters")
    if isinstance(pack_size, bool):
        raise CoinValidationError("Pack size must be a positive integer")
    try:
        pack_size = int(pack_size)
    except (TypeError, ValueError) as exc:
        raise CoinValidationError("Pack size must be a positive integer") from exc
    if pack_size < 1 or pack_size > MAX_QUANTITY:
        raise CoinValidationError(f"Pack size must be between 1 and {MAX_QUANTITY}")
    duplicate = connection.execute(
        "SELECT 1 FROM coin_items WHERE name = ? COLLATE NOCASE AND id <> ?",
        (name, item_id),
    ).fetchone()
    if duplicate:
        raise CoinValidationError("An item with that name already exists")
    try:
        updated = CoinRepository(connection).update_item(item_id, name, pack_size)
        if not updated:
            raise CoinNotFoundError("Coin item not found")
        connection.commit()
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise CoinValidationError("An item with that name already exists") from exc
    logger.info("coin_item_updated item_id=%s name=%s pack_size=%s", item_id, name, pack_size)
    return {"item_id": item_id, "name": name, "pack_size": pack_size}


def record_movement(connection, *, item, member_id, action, quantity=1, source="web", idempotency_key=None):
    if action not in VALID_ACTIONS:
        raise CoinValidationError("Unknown coin action")
    if isinstance(quantity, bool):
        raise CoinValidationError("Quantity must be a positive integer")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError) as exc:
        raise CoinValidationError("Quantity must be a positive integer") from exc
    if quantity < 1 or quantity > MAX_QUANTITY:
        raise CoinValidationError(f"Quantity must be between 1 and {MAX_QUANTITY}")
    try:
        member_id = int(member_id)
    except (TypeError, ValueError) as exc:
        raise CoinValidationError("Member is required") from exc

    repo = CoinRepository(connection)
    item_row = repo.find_item(item)
    if item_row is None:
        raise CoinNotFoundError("Coin item not found")
    if connection.execute("SELECT 1 FROM members WHERE id = ?", (member_id,)).fetchone() is None:
        raise CoinNotFoundError("Member not found")

    key = str(idempotency_key or secrets.token_urlsafe(24))
    existing = repo.movement_by_key(key)
    if existing is not None:
        expected_delta = VALID_ACTIONS[action] * quantity
        if (
            int(existing["item_id"]) != int(item_row["id"])
            or int(existing["member_id"]) != member_id
            or int(existing["inventory_delta"]) != expected_delta
            or existing["kind"] != action
        ):
            raise CoinValidationError("Idempotency key was already used for another action")
        return _result(repo, item_row, member_id, existing, replayed=True)

    delta = VALID_ACTIONS[action] * quantity
    try:
        movement_id = repo.insert_movement(item_row["id"], member_id, delta, action, source, key)
        movement = connection.execute("SELECT * FROM coin_movements WHERE id = ?", (movement_id,)).fetchone()
        result = _result(repo, item_row, member_id, movement, replayed=False)
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        existing = repo.movement_by_key(key)
        if existing is None:
            raise
        return _result(repo, item_row, member_id, existing, replayed=True)
    logger.info("coin_movement_recorded movement_id=%s item_id=%s member_id=%s kind=%s inventory_delta=%s coin_delta=%s source=%s resulting_stock=%s resulting_coin_balance=%s", movement_id, item_row["id"], member_id, action, delta, delta, source, result["resulting_stock"], result["resulting_coin_balance"])
    return result


def adjust_inventory(connection, *, item, member_id, inventory_delta, note=None, idempotency_key=None):
    """Adjust physical stock without changing any member's coin balance."""
    try:
        inventory_delta = int(inventory_delta)
    except (TypeError, ValueError) as exc:
        raise CoinValidationError("Adjustment must be a non-zero integer") from exc
    if inventory_delta == 0 or abs(inventory_delta) > MAX_QUANTITY:
        raise CoinValidationError(f"Adjustment must be between -{MAX_QUANTITY} and {MAX_QUANTITY}, excluding zero")
    repo = CoinRepository(connection)
    item_row = repo.find_item(item)
    if item_row is None:
        raise CoinNotFoundError("Coin item not found")
    key = str(idempotency_key or secrets.token_urlsafe(24))
    existing = repo.movement_by_key(key)
    if existing is not None:
        if existing["kind"] != "adjustment" or int(existing["inventory_delta"]) != inventory_delta:
            raise CoinValidationError("Idempotency key was already used for another action")
        return _result(repo, item_row, member_id, existing, replayed=True)
    try:
        movement_id = repo.insert_adjustment(item_row["id"], member_id, inventory_delta, key, note)
        movement = connection.execute("SELECT * FROM coin_movements WHERE id = ?", (movement_id,)).fetchone()
        result = _result(repo, item_row, member_id, movement, replayed=False)
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise
    logger.info("coin_inventory_adjusted movement_id=%s item_id=%s member_id=%s inventory_delta=%s resulting_stock=%s", movement_id, item_row["id"], member_id, inventory_delta, result["resulting_stock"])
    return result


def _result(repo, item_row, member_id, movement, replayed):
    return {
        "movement_id": int(movement["id"]),
        "item_id": int(item_row["id"]),
        "item": item_row["name"],
        "inventory_delta": int(movement["inventory_delta"]),
        "coin_delta": int(movement["coin_delta"]),
        "resulting_stock": repo.item_stock(item_row["id"]),
        "resulting_coin_balance": repo.member_balance(member_id),
        "replayed": replayed,
    }
