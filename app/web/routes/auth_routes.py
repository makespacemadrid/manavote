import logging
from contextlib import closing
from urllib.parse import urlencode

import requests
from authlib.integrations.base_client.errors import OAuthError
from authlib.jose.errors import JoseError
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from urllib.parse import urlparse

from app.extensions import limiter, oauth
from app.services import auth_service
from app.repositories.member_repo import MemberRepository
from app.services import feedback_service
from app.services.telegram_link_service import (
    link_member_telegram,
    read_browser_link_token,
    unlink_member_telegram,
)
from app.web.routes.helpers.admin_audit_helpers import log_telegram_link_event
from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


@auth_bp.route("/telegram/link/<token>", methods=["GET", "POST"], endpoint="telegram_link")
def telegram_link(token):
    identity = read_browser_link_token(current_app.secret_key, token)
    if identity is None:
        flash("This Telegram link is invalid or has expired. Send /link to the bot again.", "error")
        destination = "auth.telegram_settings" if "member_id" in session else "auth.login"
        return redirect(url_for(destination))
    if "member_id" not in session:
        session["login_next"] = request.path
        flash("Log in to ManaVote to connect your Telegram account.", "info")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        success, reason = link_member_telegram(
            legacy.get_db,
            session["member_id"],
            identity["telegram_username"],
            identity["telegram_user_id"],
        )
        if success:
            log_telegram_link_event(
                logger,
                event="telegram_link_updated",
                actor_id=session["member_id"],
                target_member_id=session["member_id"],
                source="browser_link",
                reason_code="ok",
                status="success",
            )
            flash("Telegram account linked.", "success")
        elif reason == "already_linked":
            flash("This Telegram account is already linked to another member.", "error")
        else:
            flash("Could not link this Telegram account.", "error")
        return redirect(url_for("auth.telegram_settings"))
    return render_template(
        "telegram_link_confirm.html",
        token=token,
        telegram_username=identity["telegram_username"],
        telegram_user_id=identity["telegram_user_id"],
        session_lang=session.get("lang", "en"),
    )


@auth_bp.route("/", endpoint="index")
def index():
    if "member_id" in session:
        return redirect(url_for("proposals"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/healthz", endpoint="healthz")
def healthz():
    return {"status": "ok"}, 200


@auth_bp.route("/login", methods=["GET", "POST"], endpoint="login")
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        with closing(legacy.get_db()) as conn:
            member = auth_service.authenticate(conn, username, password)

        if member:
            session["member_id"] = member["id"]
            session["username"] = member["username"]
            session["is_admin"] = member["is_admin"]
            if "lang" not in session:
                session["lang"] = "en"
            session.permanent = True

            next_url = session.pop("login_next", None)
            if next_url and not urlparse(next_url).netloc and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("proposals"))

        flash("Invalid credentials", "error")

    return render_template(
        "login.html",
        session_lang=session.get("lang", "en"),
        oidc_enabled=current_app.config["OIDC_ENABLED"],
    )


@auth_bp.route("/auth/login/keycloak", endpoint="keycloak_login")
@limiter.limit("10 per minute")
def keycloak_login():
    """Start Authorization Code flow; Authlib generates state, nonce and PKCE."""
    if not current_app.config["OIDC_ENABLED"]:
        abort(503, description="Makespace SSO is not configured")
    redirect_uri = current_app.config["OIDC_REDIRECT_URI"] or url_for(
        "auth.keycloak_callback", _external=True
    )
    return oauth.keycloak.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/callback/keycloak", endpoint="keycloak_callback")
@limiter.limit("10 per minute")
def keycloak_callback():
    """Validate the OIDC response and provision/update the local member."""
    if not current_app.config["OIDC_ENABLED"]:
        abort(503, description="Makespace SSO is not configured")

    try:
        token = oauth.keycloak.authorize_access_token()
    except (OAuthError, JoseError, requests.RequestException, KeyError, ValueError) as exc:
        logger.warning(
            "oidc_callback_failure reason_code=oidc_token_exchange_failed error_type=%s",
            type(exc).__name__,
            exc_info=True,
        )
        flash("Makespace SSO login failed. Please try again.", "error")
        return redirect(url_for("auth.login"))

    # authorize_access_token parses and validates the signed ID token against
    # discovery/JWKS, including nonce, issuer, audience and expiry.
    claims = token.get("userinfo") or {}
    subject = claims.get("sub")
    if not subject:
        abort(400, description="The identity response has no subject")

    groups = claims.get("groups") if isinstance(claims.get("groups"), list) else []
    required_group = current_app.config["OIDC_REQUIRED_GROUP"]
    if required_group and required_group not in groups:
        logger.warning("OIDC login rejected for subject without required group")
        session.clear()
        abort(403, description="An active Makespace membership is required")

    preferred_language = session.get("lang", "en")
    next_url = session.get("login_next")
    member = _upsert_oidc_member(claims)
    session.clear()  # Prevent session fixation and discard OIDC transient values.
    session["member_id"] = member["id"]
    session["username"] = member["username"]
    session["is_admin"] = member["is_admin"]
    session["lang"] = preferred_language
    session["oidc_login"] = True
    session.permanent = True
    if next_url and not urlparse(next_url).netloc and next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("proposals"))


def _upsert_oidc_member(claims):
    with closing(legacy.get_db()) as conn:
        return auth_service.upsert_oidc_member(conn, claims)


@auth_bp.route("/logout", endpoint="logout")
def logout():
    used_oidc = session.get("oidc_login", False)
    session.clear()
    if used_oidc and current_app.config["OIDC_ENABLED"]:
        post_logout_uri = current_app.config["OIDC_POST_LOGOUT_REDIRECT_URI"] or url_for(
            "auth.login", _external=True
        )
        params = urlencode(
            {
                "client_id": current_app.config["OIDC_CLIENT_ID"],
                "post_logout_redirect_uri": post_logout_uri,
            }
        )
        return redirect(f"{current_app.config['OIDC_ISSUER']}/protocol/openid-connect/logout?{params}")
    return redirect(url_for("auth.login"))


@auth_bp.route("/set-language/<lang>", endpoint="set_language")
def set_language(lang):
    if lang in ("en", "es"):
        session["lang"] = lang
        session.permanent = True
    return redirect(request.headers.get("Referer", url_for("proposals")))


@auth_bp.route("/change-password", methods=["GET", "POST"], endpoint="change_password")
@login_required
def change_password():
    if request.method == "POST":
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        with closing(legacy.get_db()) as conn:
            error = auth_service.change_password(conn, session["member_id"], new_password, confirm_password)
        if error:
            flash(error, "error")
            return redirect(url_for("auth.change_password"))

        flash("Password changed successfully!", "success")
        return redirect(url_for("proposals"))

    return render_template("change_password.html", session_lang=session.get("lang", "en"))


@auth_bp.route("/telegram-settings", methods=["GET", "POST"], endpoint="telegram_settings")
@login_required
def telegram_settings():
    with closing(legacy.get_db()) as conn:

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
                flash("Telegram account fields are read-only here. Send /link to the bot in a private chat.", "info")
            return redirect(url_for("auth.telegram_settings"))

        member = MemberRepository(conn).get_by_id(session["member_id"])

        return render_template(
            "telegram_settings.html",
            telegram_username=(member["telegram_username"] if member else None),
            telegram_user_id=(member["telegram_user_id"] if member else None),
            missing_public_username=bool(member and member["telegram_user_id"] and not (member["telegram_username"] or "").strip()),
            session_lang=session.get("lang", "en"),
        )


@auth_bp.route("/settings", methods=["GET", "POST"], endpoint="settings_page")
@login_required
def settings_page():
    with closing(legacy.get_db()) as conn:
        member = MemberRepository(conn).get_by_id(session["member_id"])

        if request.method == "POST":
            if request.form.get("action") == "submit_feedback":
                try:
                    feedback_service.submit_feedback(
                        conn, member_id=session["member_id"], source="web",
                        category=request.form.get("category"), message=request.form.get("message"),
                        section=request.form.get("section"),
                        logger=current_app.logger,
                    )
                    flash("Feedback submitted. Thank you!", "success")
                except feedback_service.FeedbackValidationError as exc:
                    flash(str(exc), "error")
                return_to = request.form.get("return_to", "")
                if not return_to.startswith("/") or return_to.startswith("//"):
                    return_to = url_for("auth.settings_page")
                return redirect(return_to)
            error = auth_service.add_member_email(conn, session["member_id"], request.form.get("email", ""))
            flash(error or "Email address added.", "error" if error else "success")
            return redirect(url_for("auth.settings_page"))

        email = (member["email"] or "").strip() if member else ""
        return render_template(
            "settings.html", email=email, session_lang=session.get("lang", "en")
        )


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

        with closing(legacy.get_db()) as conn:
            member_id = auth_service.register_member(conn, username, password)
        if member_id is None:
            flash("Username already exists", "error")
            return render_template("register.html", session_lang=session.get("lang", "en"))

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template(
        "register.html", session_lang=session.get("lang", "en")
    )
