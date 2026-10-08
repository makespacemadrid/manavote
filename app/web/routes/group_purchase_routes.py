import os
import secrets
from contextlib import closing

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from app.services import group_purchase_service as purchases_service
from app.repositories.group_purchase_repo import GroupPurchaseRepository
from app.services.group_purchase_service import (
    _component_names, _component_specs, _component_specs_from_fields, _shared_cost_specs,
    _allocate_shared_costs, _valid_product_url, _valid_deadline,
)
from app.web.decorators import login_required
from app.web.routes import main_routes as legacy
from translations import TRANSLATIONS


group_purchase_bp = Blueprint("group_purchases", __name__)


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
@group_purchase_bp.route(
    "/group-purchases/new", methods=["GET", "POST"], endpoint="new_purchase"
)
@login_required
def group_purchases_page():
    legacy.ensure_db_ready()
    with closing(legacy.get_db()) as conn:

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
            error = purchases_service.validate_creation(
                title=title, components=components, deadline=deadline, product_url=product_url,
                payment_method=payment_method, component_error=component_error, shared_cost_error=shared_cost_error,
            )
            if error:
                flash(error, "error")
            else:
                try:
                    image_filename = _save_image(request.files.get("image"))
                except ValueError as exc:
                    flash(str(exc), "error")
                    image_filename = False
                if image_filename is False:
                    pass
                else:
                    purchase_id = purchases_service.create_purchase(
                        conn, title=title, description=description, deadline=deadline, product_url=product_url,
                        image_filename=image_filename, payment_method=payment_method, member_id=session["member_id"],
                        components=components, shared_costs=shared_costs,
                    )
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

        purchases = purchases_service.build_purchase_page(conn, session["member_id"])
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
            show_create_form=(
                request.endpoint == "group_purchases.new_purchase" or request.method == "POST"
            ),
        )


@group_purchase_bp.post("/group-purchases/<int:purchase_id>/quantity")
@login_required
def set_quantity(purchase_id):
    legacy.ensure_db_ready()
    component_id = request.form.get("component_id", type=int)
    quantity = request.form.get("quantity", type=int)
    with closing(legacy.get_db()) as conn:
        try:
            purchases_service.set_quantity(conn, purchase_id=purchase_id, component_id=component_id,
                                           member_id=session["member_id"], quantity=quantity)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("group_purchases.group_purchases_page"))
    flash("Quantity updated", "success")
    return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")


def _manageable_purchase(cursor, purchase_id):
    return purchases_service.manageable_purchase(cursor.connection, purchase_id, session["member_id"], session.get("is_admin"))


def _creator_purchase(cursor, purchase_id):
    return purchases_service.manageable_purchase(cursor.connection, purchase_id, session["member_id"])


@group_purchase_bp.route("/group-purchases/<int:purchase_id>/edit", methods=["GET", "POST"])
@login_required
def edit_purchase(purchase_id):
    legacy.ensure_db_ready()
    with closing(legacy.get_db()) as conn:
        purchase = purchases_service.manageable_purchase(conn, purchase_id, session["member_id"], session.get("is_admin"))
        if purchase is None:
            flash("Only the creator or an admin can edit this group purchase", "error")
            return redirect(url_for("group_purchases.group_purchases_page"))

        repo = GroupPurchaseRepository(conn)
        components = repo.components(purchase_id)
        shared_cost_rows = repo.shared_costs(purchase_id)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            deadline = request.form.get("deadline", "").strip()
            product_url = request.form.get("url", "").strip()
            payment_method = request.form.get("payment_method", "").strip()
            component_updates, invalid_component = purchases_service.component_updates(
                purchase_id, components,
                [(request.form.get(f"component_name_{c['id']}", ""), request.form.get(f"component_price_{c['id']}", "0")) for c in components],
            )
            try:
                shared_costs = _shared_cost_specs(
                    request.form.getlist("cost_label"), request.form.getlist("cost_amount")
                )
            except ValueError as exc:
                shared_costs = []
                shared_cost_error = str(exc)
            else:
                shared_cost_error = None

            error = purchases_service.validate_edit(
                title=title, deadline=deadline, product_url=product_url, payment_method=payment_method,
                invalid_component=invalid_component, shared_cost_error=shared_cost_error,
            )
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
                    purchases_service.edit_purchase(
                        conn, purchase_id=purchase_id, member_id=session["member_id"], is_admin=session.get("is_admin"),
                        title=title, description=description, deadline=deadline, product_url=product_url,
                        image_filename=image_filename, payment_method=payment_method,
                        updates=component_updates, shared_costs=shared_costs,
                    )
                    flash("Group purchase updated", "success")
                    return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")

        purchase_data = dict(purchase)
        if request.method == "POST":
            purchase_data.update(request.form)
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


@group_purchase_bp.post("/group-purchases/<int:purchase_id>/delete")
@login_required
def delete_purchase(purchase_id):
    legacy.ensure_db_ready()
    with closing(legacy.get_db()) as conn:
        try:
            purchase = purchases_service.delete_purchase(conn, purchase_id=purchase_id,
                member_id=session["member_id"], is_admin=session.get("is_admin"))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("group_purchases.group_purchases_page"))

        image_filename = purchase["image_filename"]
        if image_filename:
            image_path = os.path.join(current_app.config["UPLOAD_FOLDER"], image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)
        flash("Group purchase deleted", "success")
        if request.form.get("return_to") == "admin" and session.get("is_admin"):
            return redirect(url_for("admin.admin", tab="group_purchases"))
        return redirect(url_for("group_purchases.group_purchases_page"))


@group_purchase_bp.post("/group-purchases/<int:purchase_id>/status")
@login_required
def update_status(purchase_id):
    requested_status = request.form.get("status", "")
    with closing(legacy.get_db()) as conn:
        try:
            purchase = purchases_service.update_status(conn, purchase_id=purchase_id,
                member_id=session["member_id"], status=requested_status)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")
    _send_status_notification(purchase, requested_status)
    flash("Group purchase status updated", "success")
    return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")


@group_purchase_bp.post("/group-purchases/<int:purchase_id>/payments/<int:member_id>")
@login_required
def update_payment(purchase_id, member_id):
    with closing(legacy.get_db()) as conn:
        try:
            purchases_service.update_payment(conn, purchase_id=purchase_id, member_id=member_id,
                actor_id=session["member_id"], received=request.form.get("received") == "1")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")
    flash("Payment updated", "success")
    return redirect(url_for("group_purchases.group_purchases_page") + f"#purchase-{purchase_id}")
