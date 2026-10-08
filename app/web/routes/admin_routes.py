from contextlib import closing
import os

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for

from app.extensions import limiter
from app.services import admin_actions_service, admin_page_service
from app.services.assistant_health_service import build_assistant_health
from app.integrations import telegram_agent
from app.web.routes.helpers.admin_audit_helpers import log_admin_backup_event, log_telegram_link_event

from app.web.decorators import admin_required, login_required
from app.web.routes import main_routes as legacy
from werkzeug.utils import secure_filename

admin_bp = Blueprint("admin", __name__)


@admin_bp.route('/admin/assistant-health', methods=['GET'], endpoint='assistant_health')
@login_required
@admin_required
def assistant_health():
    response = legacy.app.json.response(build_assistant_health(
        legacy._telegram_jobs, legacy._telegram_agent_executor, legacy._telegram_member_admission,
        configured=telegram_agent.is_configured(),
    ))
    response.headers['Cache-Control'] = 'no-store'
    return response


def _admin_form_data(form):
    """Keep required form fields as HTTP 400 errors before service dispatch."""
    required_fields = {
        "add_member": ("username", "password"),
        "edit_member_identity": ("member_id",),
        "remove_member": ("member_id",),
        "toggle_admin": ("member_id",),
        "unlink_telegram": ("member_id",),
        "add_budget": ("amount", "description"),
    }
    data = form.to_dict()
    for field in required_fields.get(form.get("action"), ()):
        data[field] = form[field]
    return data


def _admin_redirect_with_tab():
    tab = request.values.get("tab", "members")
    allowed_tabs = {
        "members", "budget", "polls", "group_purchases", "coins", "feedback", "settings"
    }
    safe_tab = tab if tab in allowed_tabs else "members"
    return redirect(url_for("admin.admin", tab=safe_tab))


def _log_backup_download_rejected(reason_code, backup_type, filename):
    log_admin_backup_event(
        legacy.app.logger,
        event="admin_backup_download_rejected",
        actor_id=session.get("member_id"),
        backup_type=backup_type,
        file_name=filename,
        reason_code=reason_code,
        status="rejected",
    )


@admin_bp.route("/admin", methods=["GET", "POST"], endpoint="admin")
@limiter.exempt
@login_required
@admin_required
def admin():
    legacy.ensure_db_ready()
    with closing(legacy.get_db()) as conn:
        for poll_id in legacy.close_expired_polls(conn):
            message = legacy.build_poll_results_message(conn, poll_id)
            if message:
                legacy.send_telegram_message(message)
        if request.method == "POST":
            messages, username = admin_actions_service.apply_admin_action(
                conn, data=_admin_form_data(request.form), actor_id=session["member_id"],
                is_admin=session.get("is_admin"),
                dependencies=admin_actions_service.AdminDependencies(
                    get_db=legacy.get_db, get_current_budget=legacy.get_current_budget,
                    get_setting_float=legacy.get_setting_float, get_setting_value=legacy.get_setting_value,
                    check_over_budget_proposals=legacy.check_over_budget_proposals,
                    sync_telegram_webhook=legacy.sync_telegram_webhook,
                    build_poll_results_message=legacy.build_poll_results_message,
                    send_telegram_message=legacy.send_telegram_message,
                    send_telegram_admin_test_message=legacy.send_telegram_admin_test_message,
                    db_path=legacy.DB_PATH, upload_folder=legacy.app.config["UPLOAD_FOLDER"],
                    telegram_admin_id=legacy.TELEGRAM_ADMIN_ID, logger=legacy.app.logger,
                ),
            )
            if username is not None:
                session["username"] = username
            for message in messages:
                flash(*message)
        model = admin_page_service.build_admin_page(
            conn, db_path=legacy.DB_PATH, get_thresholds=legacy.get_thresholds,
            is_registration_enabled=legacy.is_registration_enabled,
            get_current_budget=legacy.get_current_budget, logger=legacy.app.logger,
        )
    requested_tab = request.values.get("tab", "all")
    allowed_tabs = {"all", "members", "budget", "polls", "group_purchases", "coins", "feedback", "settings"}
    return render_template(
        "admin.html", **model, get_setting_value=legacy.get_setting_value,
        session_lang=session.get("lang", "en"),
        active_admin_tab=requested_tab if requested_tab in allowed_tabs else "all",
    )



@admin_bp.route("/check-overbudget", endpoint="check_overbudget")
@login_required
def check_overbudget():
    legacy.check_over_budget_proposals()
    return "OK"


@admin_bp.route("/admin/backups/<backup_type>/<filename>", endpoint="download_backup_file")
@legacy.admin_required
def download_backup_file(backup_type, filename):
    from app.services.backup_service import BACKUP_ROOT

    safe_name = secure_filename(filename or "")
    if safe_name != filename:
        _log_backup_download_rejected("invalid_filename", backup_type, filename)
        flash("Invalid backup filename", "error")
        return _admin_redirect_with_tab()

    if backup_type == "db":
        expected_prefix = f"{os.path.basename(legacy.DB_PATH).replace('.db', '')}_"
        valid = safe_name.startswith(expected_prefix) and safe_name.endswith(".db")
    elif backup_type == "images":
        valid = safe_name.startswith("uploads_") and safe_name.endswith(".zip")
    else:
        _log_backup_download_rejected("invalid_backup_type", backup_type, safe_name)
        flash("Invalid backup type", "error")
        return _admin_redirect_with_tab()

    if not valid:
        _log_backup_download_rejected("invalid_backup_file", backup_type, safe_name)
        flash("Invalid backup file", "error")
        return _admin_redirect_with_tab()

    filepath = os.path.join(BACKUP_ROOT, safe_name)
    if not os.path.isfile(filepath):
        _log_backup_download_rejected("backup_not_found", backup_type, safe_name)
        flash("Backup file not found", "error")
        return _admin_redirect_with_tab()

    actor_id = session.get("member_id")
    log_admin_backup_event(
        legacy.app.logger,
        event="admin_backup_download",
        actor_id=actor_id,
        backup_type=backup_type,
        file_name=safe_name,
        status="ok",
        file_size_bytes=os.path.getsize(filepath),
    )

    return send_file(filepath, as_attachment=True, download_name=safe_name)
