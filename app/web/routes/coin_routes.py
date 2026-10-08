"""Member Koins ledger, QR scan, and printable-label routes."""

import io
import secrets

import qrcode
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for

from app.repositories.coin_repo import CoinRepository
from app.repositories.settings_repo import SettingsRepository
from app.services import coin_service
from app.services.coin_service import CoinNotFoundError, CoinValidationError, adjust_inventory, create_item, delete_item, record_movement, update_item, update_movement
from app.web.decorators import admin_required, login_required
from app.web.routes import main_routes as legacy

coin_bp = Blueprint("coins", __name__)


def _ensure_tokens(connection):
    return coin_service.ensure_qr_tokens(connection)


def _token_row(connection, token):
    return CoinRepository(connection).get_active_token(token)


def _public_scan_url(connection, token):
    base_url = str(SettingsRepository(connection).get_value("url", "")).strip().rstrip("/")
    path = url_for("coins.scan", token=token)
    return f"{base_url}{path}" if base_url else url_for("coins.scan", token=token, _external=True)


@coin_bp.get("/koins")
@login_required
def coins_page():
    connection = legacy.get_db()
    repo = CoinRepository(connection)
    items = repo.list_items(session["member_id"])
    balance = repo.member_balance(session["member_id"])
    rankings = repo.member_rankings()
    movements = repo.recent_movements()
    connection.close()
    return render_template(
        "coins.html", items=items, balance=balance, rankings=rankings, movements=movements
    )


@coin_bp.post("/koins/move")
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
        flash(f"{result['item']}: {result['coin_delta']:+d} koins; balance {result['resulting_coin_balance']}", "success")
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return_to = request.form.get("return_to", "")
    if not return_to.startswith("/") or return_to.startswith("//"):
        return_to = url_for("coins.coins_page")
    return redirect(return_to)


@coin_bp.get("/koins/scan/<token>")
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


@coin_bp.get("/koins/qr/<token>.png")
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


@coin_bp.get("/admin/koins/qr-labels")
@login_required
@admin_required
def qr_labels():
    connection = legacy.get_db()
    _ensure_tokens(connection)
    labels = [dict(row) for row in CoinRepository(connection).list_consume_labels()]
    repo = CoinRepository(connection)
    items = repo.list_items()
    movements = repo.recent_movements(limit=100)
    connection.close()
    return render_template("coin_qr_labels.html", labels=labels, items=items, movements=movements)


@coin_bp.post("/admin/koins/qr-tokens/<int:item_id>/<action>")
@login_required
@admin_required
def update_qr_token(item_id, action):
    if action != "consume":
        abort(404)
    operation = request.form.get("operation")
    connection = legacy.get_db()
    try:
        coin_service.update_qr_token(connection, item_id=item_id, action=action, operation=operation)
    except CoinValidationError:
        abort(400)
    finally:
        connection.close()
    if operation == "rotate":
        flash("QR token rotated. Previously printed labels no longer work.", "success")
    else:
        flash("QR token updated", "success")
    current_app.logger.info(
        "coin_qr_token_updated item_id=%s action=%s operation=%s member_id=%s",
        item_id,
        action,
        operation,
        session["member_id"],
    )
    return redirect(url_for("coins.qr_labels"))


@coin_bp.post("/admin/koins/adjust")
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
        flash("Koin inventory adjusted", "success")
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return redirect(url_for("coins.qr_labels"))


@coin_bp.post("/admin/koins/movements/<int:movement_id>")
@login_required
@admin_required
def edit_movement(movement_id):
    connection = legacy.get_db()
    try:
        update_movement(
            connection, movement_id=movement_id, item=request.form.get("item_id"),
            member_id=request.form.get("member_id"), kind=request.form.get("kind"),
            quantity=request.form.get("quantity"), note=request.form.get("note"),
        )
        flash("Koin movement updated", "success")
        current_app.logger.info("coin_movement_updated_by_admin movement_id=%s member_id=%s", movement_id, session["member_id"])
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return redirect(url_for("admin.admin", tab="coins"))


@coin_bp.post("/admin/koins/items")
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
        flash("Koin item created", "success")
    except CoinValidationError as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    if request.form.get("return_to") == "admin":
        return redirect(url_for("admin.admin", tab="coins"))
    return redirect(url_for("coins.qr_labels"))


@coin_bp.post("/admin/koins/items/<int:item_id>")
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
        flash("Koin item updated", "success")
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return redirect(url_for("admin.admin", tab="coins"))


@coin_bp.post("/admin/koins/items/<int:item_id>/delete")
@login_required
@admin_required
def delete_coin_item(item_id):
    connection = legacy.get_db()
    try:
        delete_item(connection, item_id=item_id)
        current_app.logger.info(
            "coin_item_deleted_by_admin item_id=%s member_id=%s",
            item_id,
            session["member_id"],
        )
        flash("Koin item deleted", "success")
    except (CoinValidationError, CoinNotFoundError) as exc:
        flash(str(exc), "error")
    finally:
        connection.close()
    return redirect(url_for("admin.admin", tab="coins"))
