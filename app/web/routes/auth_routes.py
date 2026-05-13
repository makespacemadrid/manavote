import logging

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from app.extensions import limiter
from app.services.auth_service import verify_and_migrate_password
from app.services.telegram_link_service import unlink_member_telegram
from app.web.routes.helpers.admin_audit_helpers import log_telegram_link_event
from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


@auth_bp.route("/", endpoint="index")
def index():
    if "member_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/healthz", endpoint="healthz")
def healthz():
    return {"status": "ok"}, 200


@auth_bp.route("/login", methods=["GET", "POST"], endpoint="login")
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = legacy.get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM members WHERE username = ?", (username,))
        member = c.fetchone()

        if member:
            stored_hash = member["password_hash"]

            valid, migrated_hash = verify_and_migrate_password(stored_hash, password)
            if migrated_hash:
                c.execute(
                    "UPDATE members SET password_hash = ? WHERE id = ?",
                    (migrated_hash, member["id"]),
                )
                conn.commit()
        else:
            valid = False

        conn.close()

        if member and valid:
            session["member_id"] = member["id"]
            session["username"] = member["username"]
            session["is_admin"] = member["is_admin"]
            if "lang" not in session:
                session["lang"] = "en"
            session.permanent = True

            return redirect(url_for("dashboard"))

        flash("Invalid credentials", "error")

    return render_template("login.html", session_lang=session.get("lang", "en"))


@auth_bp.route("/logout", endpoint="logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/set-language/<lang>", endpoint="set_language")
def set_language(lang):
    if lang in ("en", "es"):
        session["lang"] = lang
        session.permanent = True
    return redirect(request.headers.get("Referer", url_for("dashboard")))


@auth_bp.route("/change-password", methods=["GET", "POST"], endpoint="change_password")
@login_required
def change_password():
    if request.method == "POST":
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if not new_password or not confirm_password:
            flash("All fields are required", "error")
            return redirect(url_for("auth.change_password"))

        if new_password != confirm_password:
            flash("New passwords do not match", "error")
            return redirect(url_for("auth.change_password"))

        if len(new_password) < 4:
            flash("Password must be at least 4 characters", "error")
            return redirect(url_for("auth.change_password"))

        new_hash = generate_password_hash(new_password)
        conn = legacy.get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE members SET password_hash = ? WHERE id = ?",
            (new_hash, session["member_id"]),
        )
        conn.commit()
        conn.close()

        flash("Password changed successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("change_password.html", session_lang=session.get("lang", "en"))


@auth_bp.route("/telegram-settings", methods=["GET", "POST"], endpoint="telegram_settings")
@login_required
def telegram_settings():
    conn = legacy.get_db()
    c = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "unlink_telegram":
            target_member_id = int(session["member_id"])
            unlink_member_telegram(legacy.get_db, target_member_id)
            log_telegram_link_event(
                logger,
                event="member_telegram_unlink",
                actor_id=target_member_id,
                target_member_id=target_member_id,
                source="member_settings",
                reason_code="self_unlink",
                status="success",
            )
            flash("Telegram account unlinked.", "success")
        else:
            flash("Telegram account fields are read-only here. Use /link <app_username> <app_password> in Telegram.", "info")
        conn.close()
        return redirect(url_for("auth.telegram_settings"))

    c.execute(
        "SELECT telegram_username, telegram_user_id FROM members WHERE id = ?",
        (session["member_id"],),
    )
    member = c.fetchone()
    conn.close()

    return render_template(
        "telegram_settings.html",
        telegram_username=(member["telegram_username"] if member else None),
        telegram_user_id=(member["telegram_user_id"] if member else None),
        missing_public_username=bool(member and member["telegram_user_id"] and not (member["telegram_username"] or "").strip()),
        session_lang=session.get("lang", "en"),
    )


@auth_bp.route("/settings", endpoint="settings_page")
@login_required
def settings_page():
    return render_template("settings.html", session_lang=session.get("lang", "en"))


@auth_bp.route("/register", methods=["GET", "POST"], endpoint="register")
def register():
    if not legacy.is_registration_enabled():
        flash(
            "Self-registration is currently disabled. Please contact an admin.",
            "error",
        )
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if not username or not password:
            flash("Username and password are required", "error")
            return render_template(
                "register.html", session_lang=session.get("lang", "en")
            )

        password_hash = generate_password_hash(password)

        conn = legacy.get_db()
        c = conn.cursor()

        c.execute("SELECT id FROM members WHERE username = ?", (username,))
        if c.fetchone():
            flash("Username already exists", "error")
            conn.close()
            return render_template(
                "register.html", session_lang=session.get("lang", "en")
            )

        c.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, 0)",
            (username, password_hash),
        )
        conn.commit()
        conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template(
        "register.html", session_lang=session.get("lang", "en")
    )
