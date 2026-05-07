from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from app.extensions import limiter
from app.services.auth_service import verify_and_migrate_password
from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

auth_bp = Blueprint("auth", __name__)


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
            return redirect(url_for("change_password"))

        if new_password != confirm_password:
            flash("New passwords do not match", "error")
            return redirect(url_for("change_password"))

        if len(new_password) < 4:
            flash("Password must be at least 4 characters", "error")
            return redirect(url_for("change_password"))

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
