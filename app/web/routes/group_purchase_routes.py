import os
import secrets
from datetime import date
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy
from translations import TRANSLATIONS


group_purchase_bp = Blueprint("group_purchases", __name__)


def _component_names(raw_components):
    """Return unique, non-empty component names while preserving their order."""
    names = []
    seen = set()
    for line in raw_components.splitlines():
        name = line.strip()
        key = name.casefold()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    return names


def _component_specs(raw_components):
    """Parse ``name | unit price`` lines; the price is optional."""
    specs = []
    seen = set()
    for line in raw_components.splitlines():
        value = line.strip()
        if not value:
            continue
        name, separator, raw_price = value.rpartition("|")
        if separator:
            name = name.strip()
            try:
                unit_price = round(float(raw_price.strip().replace(",", ".")), 2)
            except ValueError as exc:
                raise ValueError("Invalid component price") from exc
        else:
            name = value
            unit_price = 0
        if not name or len(name) > 100 or unit_price < 0 or unit_price > 1000000:
            raise ValueError("Invalid component name or price")
        key = name.casefold()
        if key not in seen:
            specs.append((name, unit_price))
            seen.add(key)
    return specs


def _component_specs_from_fields(names, prices):
    """Validate component rows submitted by the purchase form."""
    lines = []
    for index, name in enumerate(names):
        price = prices[index] if index < len(prices) else ""
        if name.strip() or price.strip():
            lines.append(f"{name} | {price or '0'}")
    return _component_specs("\n".join(lines))


def _shared_cost_specs(labels, amounts):
    """Validate shared costs such as shipping, customs, or taxes."""
    costs = []
    for index, label in enumerate(labels):
        amount = amounts[index] if index < len(amounts) else ""
        if not label.strip() and not amount.strip():
            continue
        try:
            value = round(float(amount.strip().replace(",", ".")), 2)
        except ValueError as exc:
            raise ValueError("Invalid shared cost") from exc
        label = label.strip()
        if not label or len(label) > 100 or value < 0 or value > 1000000:
            raise ValueError("Invalid shared cost")
        costs.append((label, value))
    if len(costs) > 20:
        raise ValueError("A group purchase can have at most 20 shared costs")
    return costs


def _allocate_shared_costs(debts, shared_cost_total):
    """Add proportional shared-cost and total fields to participant debts."""
    selection_total = sum(debt["selection_amount"] for debt in debts)
    allocated = 0.0
    for index, debt in enumerate(debts):
        percentage = debt["selection_amount"] / selection_total if selection_total else 0
        debt["selection_percentage"] = percentage * 100
        if selection_total and index == len(debts) - 1:
            debt["shared_cost_share"] = round(shared_cost_total - allocated, 2)
        else:
            debt["shared_cost_share"] = round(shared_cost_total * percentage, 2)
            allocated += debt["shared_cost_share"]
        debt["amount_owed"] = round(debt["selection_amount"] + debt["shared_cost_share"], 2)
    return debts


def _valid_product_url(url):
    if not url:
        return True
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_deadline(deadline):
    try:
        date.fromisoformat(deadline)
        return True
    except ValueError:
        return False


def _save_image(image):
    if not image or not image.filename:
        return None
    extension = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
    if extension not in {"jpg", "jpeg", "png"}:
        raise ValueError("Invalid image format")

    filename = f"group-{secrets.token_hex(8)}.{extension}"
    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    image.save(filepath)
    if legacy.detect_image_type(filepath) not in {"jpeg", "png"}:
        os.remove(filepath)
        raise ValueError("Invalid image format")
    return filename


def _send_status_notification(purchase, status):
    catalog = TRANSLATIONS.get(session.get("lang", "en"), TRANSLATIONS["en"])
    status_labels = {
        "ordered": "📦 " + catalog["Order placed"],
        "received": "✅ " + catalog["Shipment received"],
    }
    details = [
        f"🛒 {catalog['Group purchase update']}: {purchase['title']}",
        status_labels[status],
        f"{catalog['By']}: {session['username'].split('@')[0]}",
    ]
    if purchase["deadline"]:
        details.append(f"📅 {catalog['Order deadline']}: {purchase['deadline']}")
    base_url = legacy.get_base_url().rstrip("/")
    if base_url:
        details.append(f"👉 {base_url}/group-purchases#purchase-{purchase['id']}")
    return legacy.send_telegram_message("\n".join(details))


@group_purchase_bp.route("/group-purchases", methods=["GET", "POST"])
@login_required
def group_purchases_page():
    legacy.ensure_db_ready()
    conn = legacy.get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        component_names = request.form.getlist("component_name")
        component_prices = request.form.getlist("component_price")
        try:
            if component_names:
                components = _component_specs_from_fields(component_names, component_prices)
            else:
                # Backwards-compatible fallback for older clients.
                components = _component_specs(request.form.get("components", ""))
        except ValueError as exc:
            components = []
            component_error = str(exc)
        else:
            component_error = None
        try:
            shared_costs = _shared_cost_specs(
                request.form.getlist("cost_label"), request.form.getlist("cost_amount")
            )
        except ValueError as exc:
            shared_costs = []
            shared_cost_error = str(exc)
        else:
            shared_cost_error = None
        deadline = request.form.get("deadline", "").strip()
        product_url = request.form.get("url", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        if component_error:
            flash(component_error, "error")
        elif shared_cost_error:
            flash(shared_cost_error, "error")
        elif not title or not components:
            flash("Add a title and at least one component", "error")
        elif len(title) > 150:
            flash("The title or a component is too long", "error")
        elif len(components) > 30:
            flash("A group purchase can have at most 30 components", "error")
        elif deadline and not _valid_deadline(deadline):
            flash("Invalid deadline", "error")
        elif not _valid_product_url(product_url):
            flash("Invalid URL", "error")
        elif len(payment_method) > 250:
            flash("Payment method is too long", "error")
        else:
            try:
                image_filename = _save_image(request.files.get("image"))
            except ValueError as exc:
                flash(str(exc), "error")
                image_filename = False
            if image_filename is False:
                pass
            else:
                cursor.execute(
                    """
                    INSERT INTO group_purchases
                        (title, description, deadline, url, image_filename, payment_method, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title,
                        description,
                        deadline or None,
                        product_url or None,
                        image_filename,
                        payment_method or None,
                        session["member_id"],
                    ),
                )
                purchase_id = cursor.lastrowid
                cursor.executemany(
                    """
                    INSERT INTO group_purchase_components
                        (group_purchase_id, name, unit_price, position)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (purchase_id, name, unit_price, position)
                        for position, (name, unit_price) in enumerate(components)
                    ],
                )
                cursor.executemany(
                    """
                    INSERT INTO group_purchase_shared_costs
                        (group_purchase_id, label, amount, position)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (purchase_id, label, amount, position)
                        for position, (label, amount) in enumerate(shared_costs)
                    ],
                )
                conn.commit()
                conn.close()
                creator = session["username"].split("@")[0]
                option_lines = "\n".join(
                    f"• {name}: €{unit_price:.2f}" for name, unit_price in components
                )
                base_url = legacy.get_base_url().rstrip("/")
                details = [
                    f"🛒 New group purchase: {title}",
                    f"By: {creator}",
                    "",
                    option_lines,
                ]
                if deadline:
                    details.append(f"📅 Deadline: {deadline}")
                if payment_method:
                    details.append(f"💳 Payment: {payment_method}")
                if shared_costs:
                    costs_text = ", ".join(f"{label}: €{amount:.2f}" for label, amount in shared_costs)
                    details.append(f"➕ Shared costs: {costs_text}")
                if product_url:
                    details.append(f"🔗 Product: {product_url}")
                if base_url:
                    details.append(f"👉 {base_url}/group-purchases#purchase-{purchase_id}")
                legacy.send_telegram_message("\n".join(details))
                flash("Group purchase created", "success")
                return redirect(url_for("group_purchases.group_purchases_page"))

    cursor.execute(
        """
        SELECT gp.*, m.username AS creator
        FROM group_purchases gp
        JOIN members m ON m.id = gp.created_by
        ORDER BY gp.created_at DESC, gp.id DESC
        """
    )
    purchases = [dict(row) for row in cursor.fetchall()]
    for purchase in purchases:
        cursor.execute(
            """
            SELECT c.id, c.name, c.unit_price, COALESCE(SUM(q.quantity), 0) AS total_quantity
            FROM group_purchase_components c
            LEFT JOIN group_purchase_quantities q ON q.component_id = c.id
            WHERE c.group_purchase_id = ?
            GROUP BY c.id, c.name, c.position
            ORDER BY c.position, c.id
            """,
            (purchase["id"],),
        )
        purchase["components"] = [dict(row) for row in cursor.fetchall()]
        for component in purchase["components"]:
            cursor.execute(
                """
                SELECT q.quantity, q.member_id, m.username
                FROM group_purchase_quantities q
                JOIN members m ON m.id = q.member_id
                WHERE q.component_id = ? AND q.quantity > 0
                ORDER BY m.username COLLATE NOCASE
                """,
                (component["id"],),
            )
            component["orders"] = [dict(row) for row in cursor.fetchall()]
            component["user_quantity"] = next(
                (
                    order["quantity"]
                    for order in component["orders"]
                    if order["member_id"] == session["member_id"]
                ),
                0,
            )
        cursor.execute(
            """
            SELECT id, label, amount FROM group_purchase_shared_costs
            WHERE group_purchase_id = ? ORDER BY position, id
            """,
            (purchase["id"],),
        )
        purchase["shared_costs"] = [dict(row) for row in cursor.fetchall()]
        purchase["shared_cost_total"] = sum(cost["amount"] for cost in purchase["shared_costs"])
        cursor.execute(
            """
            SELECT m.id AS member_id, m.username,
                   SUM(q.quantity * c.unit_price) AS selection_amount,
                   pp.received_at
            FROM group_purchase_quantities q
            JOIN group_purchase_components c ON c.id = q.component_id
            JOIN members m ON m.id = q.member_id
            LEFT JOIN group_purchase_payments pp
              ON pp.group_purchase_id = c.group_purchase_id AND pp.member_id = m.id
            WHERE c.group_purchase_id = ? AND q.quantity > 0
            GROUP BY m.id, m.username, pp.received_at
            ORDER BY m.username COLLATE NOCASE
            """,
            (purchase["id"],),
        )
        purchase["debts"] = [dict(row) for row in cursor.fetchall()]
        _allocate_shared_costs(purchase["debts"], purchase["shared_cost_total"])
    conn.close()
    return render_template(
        "group_purchases.html",
        purchases=purchases,
        submitted=request.form if request.method == "POST" else {},
        submitted_components=(
            list(zip(request.form.getlist("component_name"), request.form.getlist("component_price")))
            or [("", "")]
            if request.method == "POST"
            else [("", "")]
        ),
        submitted_costs=(
            list(zip(request.form.getlist("cost_label"), request.form.getlist("cost_amount")))
            if request.method == "POST"
            else []
        ),
        session_lang=session.get("lang", "en"),
    )


@group_purchase_bp.post("/group-purchases/<int:purchase_id>/quantity")
@login_required
def set_quantity(purchase_id):
    legacy.ensure_db_ready()
    component_id = request.form.get("component_id", type=int)
    quantity = request.form.get("quantity", type=int)
    if component_id is None or quantity is None or quantity < 0 or quantity > 999:
        flash("Quantity must be between 0 and 999", "error")
        return redirect(url_for("group_purchases.group_purchases_page"))

    conn = legacy.get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.id FROM group_purchase_components c
        JOIN group_purchases gp ON gp.id = c.group_purchase_id
        WHERE c.id = ? AND gp.id = ? AND gp.status = 'open'
        """,
        (component_id, purchase_id),
    )
    if cursor.fetchone() is None:
        conn.close()
        flash("Component not found", "error")
        return redirect(url_for("group_purchases.group_purchases_page"))

    if quantity == 0:
        cursor.execute(
            "DELETE FROM group_purchase_quantities WHERE component_id = ? AND member_id = ?",
            (component_id, session["member_id"]),
        )
    else:
        cursor.execute(
            """
            INSERT INTO group_purchase_quantities (component_id, member_id, quantity, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(component_id, member_id) DO UPDATE SET
                quantity = excluded.quantity,
                updated_at = CURRENT_TIMESTAMP
            """,
            (component_id, session["member_id"], quantity),
        )
    conn.commit()
    conn.close()
    flash("Quantity updated", "success")
    return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")


def _creator_purchase(cursor, purchase_id):
    cursor.execute(
        "SELECT * FROM group_purchases WHERE id = ? AND created_by = ?",
        (purchase_id, session["member_id"]),
    )
    return cursor.fetchone()


@group_purchase_bp.route("/group-purchases/<int:purchase_id>/edit", methods=["GET", "POST"])
@login_required
def edit_purchase(purchase_id):
    legacy.ensure_db_ready()
    conn = legacy.get_db()
    cursor = conn.cursor()
    purchase = _creator_purchase(cursor, purchase_id)
    if purchase is None:
        conn.close()
        flash("Only the creator can edit this group purchase", "error")
        return redirect(url_for("group_purchases.group_purchases_page"))
    if purchase["status"] != "open":
        conn.close()
        flash("An order can only be edited before it is placed", "error")
        return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")

    cursor.execute(
        "SELECT * FROM group_purchase_components WHERE group_purchase_id = ? ORDER BY position, id",
        (purchase_id,),
    )
    components = cursor.fetchall()
    cursor.execute(
        "SELECT * FROM group_purchase_shared_costs WHERE group_purchase_id = ? ORDER BY position, id",
        (purchase_id,),
    )
    shared_cost_rows = cursor.fetchall()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline = request.form.get("deadline", "").strip()
        product_url = request.form.get("url", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        component_updates = []
        invalid_component = False
        for component in components:
            name = request.form.get(f"component_name_{component['id']}", "").strip()
            raw_price = request.form.get(f"component_price_{component['id']}", "0")
            try:
                price = round(float(raw_price), 2)
            except (TypeError, ValueError):
                invalid_component = True
                break
            if not name or len(name) > 100 or price < 0 or price > 1000000:
                invalid_component = True
                break
            component_updates.append((name, price, component["id"], purchase_id))
        try:
            shared_costs = _shared_cost_specs(
                request.form.getlist("cost_label"), request.form.getlist("cost_amount")
            )
        except ValueError as exc:
            shared_costs = []
            shared_cost_error = str(exc)
        else:
            shared_cost_error = None

        error = None
        if not title or len(title) > 150:
            error = "Invalid title"
        elif deadline and not _valid_deadline(deadline):
            error = "Invalid deadline"
        elif not _valid_product_url(product_url):
            error = "Invalid URL"
        elif len(payment_method) > 250:
            error = "Payment method is too long"
        elif invalid_component:
            error = "Invalid component name or price"
        elif shared_cost_error:
            error = shared_cost_error
        if error:
            flash(error, "error")
        else:
            image_filename = purchase["image_filename"]
            try:
                new_image = _save_image(request.files.get("image"))
            except ValueError as exc:
                flash(str(exc), "error")
            else:
                if new_image:
                    old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], image_filename or "")
                    if image_filename and os.path.exists(old_path):
                        os.remove(old_path)
                    image_filename = new_image
                cursor.execute(
                    """
                    UPDATE group_purchases
                    SET title = ?, description = ?, deadline = ?, url = ?, image_filename = ?, payment_method = ?
                    WHERE id = ? AND created_by = ?
                    """,
                    (
                        title,
                        description,
                        deadline or None,
                        product_url or None,
                        image_filename,
                        payment_method or None,
                        purchase_id,
                        session["member_id"],
                    ),
                )
                cursor.executemany(
                    """
                    UPDATE group_purchase_components SET name = ?, unit_price = ?
                    WHERE id = ? AND group_purchase_id = ?
                    """,
                    component_updates,
                )
                cursor.execute(
                    "DELETE FROM group_purchase_shared_costs WHERE group_purchase_id = ?",
                    (purchase_id,),
                )
                cursor.executemany(
                    """
                    INSERT INTO group_purchase_shared_costs
                        (group_purchase_id, label, amount, position)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (purchase_id, label, amount, position)
                        for position, (label, amount) in enumerate(shared_costs)
                    ],
                )
                conn.commit()
                conn.close()
                flash("Group purchase updated", "success")
                return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")

    purchase_data = dict(purchase)
    if request.method == "POST":
        purchase_data.update(request.form)
    conn.close()
    return render_template(
        "edit_group_purchase.html",
        purchase=purchase_data,
        components=components,
        shared_costs=(
            list(zip(request.form.getlist("cost_label"), request.form.getlist("cost_amount")))
            if request.method == "POST"
            else [(row["label"], row["amount"]) for row in shared_cost_rows]
        ),
        session_lang=session.get("lang", "en"),
    )


@group_purchase_bp.post("/group-purchases/<int:purchase_id>/status")
@login_required
def update_status(purchase_id):
    requested_status = request.form.get("status", "")
    transitions = {"open": "ordered", "ordered": "received"}
    conn = legacy.get_db()
    cursor = conn.cursor()
    purchase = _creator_purchase(cursor, purchase_id)
    if purchase is None or transitions.get(purchase["status"]) != requested_status:
        conn.close()
        flash("Invalid status change", "error")
        return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")
    cursor.execute("UPDATE group_purchases SET status = ? WHERE id = ?", (requested_status, purchase_id))
    conn.commit()
    conn.close()
    _send_status_notification(purchase, requested_status)
    flash("Group purchase status updated", "success")
    return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")


@group_purchase_bp.post("/group-purchases/<int:purchase_id>/payments/<int:member_id>")
@login_required
def update_payment(purchase_id, member_id):
    conn = legacy.get_db()
    cursor = conn.cursor()
    purchase = _creator_purchase(cursor, purchase_id)
    cursor.execute(
        """
        SELECT 1 FROM group_purchase_quantities q
        JOIN group_purchase_components c ON c.id = q.component_id
        WHERE c.group_purchase_id = ? AND q.member_id = ? AND q.quantity > 0
        LIMIT 1
        """,
        (purchase_id, member_id),
    )
    participant = cursor.fetchone()
    if purchase is None or participant is None:
        conn.close()
        flash("Payment cannot be updated", "error")
        return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")
    if request.form.get("received") == "1":
        cursor.execute(
            "INSERT OR REPLACE INTO group_purchase_payments (group_purchase_id, member_id) VALUES (?, ?)",
            (purchase_id, member_id),
        )
    else:
        cursor.execute(
            "DELETE FROM group_purchase_payments WHERE group_purchase_id = ? AND member_id = ?",
            (purchase_id, member_id),
        )
    conn.commit()
    conn.close()
    flash("Payment updated", "success")
    return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")
