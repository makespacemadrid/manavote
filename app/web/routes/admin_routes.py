import os

from flask import Blueprint, flash, redirect, request, send_file, session, url_for

from app.extensions import limiter
from app.web.routes.helpers.admin_audit_helpers import log_admin_backup_event

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy
from werkzeug.utils import secure_filename

admin_bp = Blueprint("admin", __name__)


def _admin_redirect_with_tab():
    tab = request.values.get("tab", "members")
    allowed_tabs = {"members", "budget", "polls", "settings"}
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
def admin():
    return legacy.admin()


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
