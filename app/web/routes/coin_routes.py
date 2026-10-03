"""Member Coins ledger, QR scan, and printable-label routes."""

import io
import secrets

import qrcode
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for

from app.repositories.coin_repo import CoinRepository
from app.services.coin_service import CoinNotFoundError, CoinValidationError, adjust_inventory, create_item, record_movement, update_item
from app.web.decorators import admin_required, login_required
from app.web.routes import main_routes as legacy

coin_bp = Blueprint("coins", __name__)


def _ensure_tokens(connection):
    for item in CoinRepository(connection).list_items():
        connection.execute(
            "INSERT OR IGNORE INTO coin_qr_tokens (token, item_id, action) VALUES (?, ?, 'consume')",
            (secrets.token_urlsafe(24), item["id"]),
        )
    connection.execute("DELETE FROM coin_qr_tokens WHERE action = 'replenish'")
    connection.commit()


def _token_row(connection, token):
    return connection.execute(
        """SELECT qt.*, ci.name AS item_name, ci.pack_size FROM coin_qr_tokens qt
           JOIN coin_items ci ON ci.id = qt.item_id
           WHERE qt.token = ? AND qt.action = 'consume' AND qt.active = 1 AND ci.active = 1""",
        (token,),
    ).fetchone()


def _public_scan_url(connection, token):
    row = connection.execute("SELECT value FROM settings WHERE key = 'url'").fetchone()
    base_url = str(row["value"] if row else "").strip().rstrip("/")
    path = url_for("coins.scan", token=token)
    return f"{base_url}{path}" if base_url else url_for("coins.scan", token=token, _external=True)


@coin_bp.get("/coins")
@login_required
def coins_page():
    connection = legacy.get_db()
    repo = CoinRepository(connection)
    items = repo.list_items(session["member_id"])
    balance = repo.member_balance(session["member_id"])
    rankings = repo.member_rankings()
    movements = repo.recent_movements(member_id=session["member_id"])
    connection.close()
    return render_template(
        "coins.html", items=items, balance=balance, rankings=rankings, movements=movements
    )


@coin_bp.post("/coins/move")
@login_required
def move():
    connection = legacy.get_db()
    try:
        result = record_movement(
            connection,
            item=request.form.get("item_id"),
            member_id=session["member_id"],
            action=request.form.get("action"),
            quantity=request.form.get("quantity", 1),
            source=request.form.get("source", "web") if request.form.get("source") in {"web", "qr"} else "web",
            idempotency_key=request.form.get("idempotency_key"),
        )
        flash(f"{result['item']}: {result['coin_delta']:+d} coins; balance {result['resulting_coin_balance']}", "success")
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return_to = request.form.get("return_to", "")
    if not return_to.startswith("/") or return_to.startswith("//"):
        return_to = url_for("coins.coins_page")
    return redirect(return_to)


@coin_bp.get("/coins/scan/<token>")
def scan(token):
    if "member_id" not in session:
        session["login_next"] = request.path
        return redirect(url_for("auth.login"))
    connection = legacy.get_db()
    row = _token_row(connection, token)
    connection.close()
    if row is None:
        abort(404)
    return render_template("coin_scan.html", token=token, qr=row, idempotency_key=secrets.token_urlsafe(24))


@coin_bp.get("/coins/qr/<token>.png")
@login_required
def qr_image(token):
    connection = legacy.get_db()
    row = _token_row(connection, token)
    if row is None:
        connection.close()
        abort(404)
    scan_url = _public_scan_url(connection, token)
    connection.close()
    image = qrcode.make(scan_url)
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return send_file(output, mimetype="image/png", max_age=0)


@coin_bp.get("/admin/coins/qr-labels")
@login_required
@admin_required
def qr_labels():
    connection = legacy.get_db()
    _ensure_tokens(connection)
    tokens = connection.execute(
        """SELECT qt.token, qt.action, ci.name AS item_name FROM coin_qr_tokens qt
           JOIN coin_items ci ON ci.id = qt.item_id
           WHERE ci.active = 1 AND qt.action = 'consume' ORDER BY ci.position"""
    ).fetchall()
    labels = []
    for label in tokens:
        item = dict(label)
        state = connection.execute("SELECT active, item_id FROM coin_qr_tokens WHERE token = ?", (label["token"],)).fetchone()
        item["active"] = state["active"]
        item["item_id"] = state["item_id"]
        labels.append(item)
    repo = CoinRepository(connection)
    items = repo.list_items()
    movements = repo.recent_movements(limit=100)
    connection.close()
    return render_template("coin_qr_labels.html", labels=labels, items=items, movements=movements)


@coin_bp.post("/admin/coins/qr-tokens/<int:item_id>/<action>")
@login_required
@admin_required
def update_qr_token(item_id, action):
    if action != "consume":
        abort(404)
    operation = request.form.get("operation")
    connection = legacy.get_db()
    if operation == "rotate":
        connection.execute(
            "UPDATE coin_qr_tokens SET token = ?, active = 1 WHERE item_id = ? AND action = ?",
            (secrets.token_urlsafe(24), item_id, action),
        )
        flash("QR token rotated. Previously printed labels no longer work.", "success")
    elif operation in {"enable", "disable"}:
        connection.execute(
            "UPDATE coin_qr_tokens SET active = ? WHERE item_id = ? AND action = ?",
            (1 if operation == "enable" else 0, item_id, action),
        )
        flash("QR token updated", "success")
    else:
        connection.close()
        abort(400)
    connection.commit()
    connection.close()
    current_app.logger.info(
        "coin_qr_token_updated item_id=%s action=%s operation=%s member_id=%s",
        item_id,
        action,
        operation,
        session["member_id"],
    )
    return redirect(url_for("coins.qr_labels"))


@coin_bp.post("/admin/coins/adjust")
@login_required
@admin_required
def adjust():
    connection = legacy.get_db()
    try:
        adjust_inventory(
            connection,
            item=request.form.get("item_id"),
            member_id=session["member_id"],
            inventory_delta=request.form.get("inventory_delta"),
            note=request.form.get("note", "").strip() or None,
            idempotency_key=request.form.get("idempotency_key"),
        )
        flash("Coin inventory adjusted", "success")
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return redirect(url_for("coins.qr_labels"))


@coin_bp.post("/admin/coins/items")
@login_required
@admin_required
def create_coin_item():
    connection = legacy.get_db()
    try:
        item = create_item(
            connection,
            name=request.form.get("name"),
            pack_size=request.form.get("pack_size"),
        )
        current_app.logger.info(
            "coin_item_created_by_admin item_id=%s member_id=%s",
            item["item_id"],
            session["member_id"],
        )
        flash("Coin item created", "success")
    except CoinValidationError as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    if request.form.get("return_to") == "admin":
        return redirect(url_for("admin.admin", tab="coins"))
    return redirect(url_for("coins.qr_labels"))


@coin_bp.post("/admin/coins/items/<int:item_id>")
@login_required
@admin_required
def edit_coin_item(item_id):
    connection = legacy.get_db()
    try:
        item = update_item(
            connection,
            item_id=item_id,
            name=request.form.get("name"),
            pack_size=request.form.get("pack_size"),
        )
        current_app.logger.info(
            "coin_item_updated_by_admin item_id=%s member_id=%s",
            item["item_id"],
            session["member_id"],
        )
        flash("Coin item updated", "success")
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return redirect(url_for("admin.admin", tab="coins"))
