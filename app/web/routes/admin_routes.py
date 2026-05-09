import os

from flask import Blueprint, flash, redirect, send_file, url_for

from app.extensions import limiter

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy
from werkzeug.utils import secure_filename

admin_bp = Blueprint("admin", __name__)


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
        flash("Invalid backup filename", "error")
        return redirect(url_for("admin.admin"))

    if backup_type == "db":
        expected_prefix = f"{os.path.basename(legacy.DB_PATH).replace('.db', '')}_"
        valid = safe_name.startswith(expected_prefix) and safe_name.endswith(".db")
    elif backup_type == "images":
        valid = safe_name.startswith("uploads_") and safe_name.endswith(".zip")
    else:
        flash("Invalid backup type", "error")
        return redirect(url_for("admin.admin"))

    if not valid:
        flash("Invalid backup file", "error")
        return redirect(url_for("admin.admin"))

    filepath = os.path.join(BACKUP_ROOT, safe_name)
    if not os.path.isfile(filepath):
        flash("Backup file not found", "error")
        return redirect(url_for("admin.admin"))

    return send_file(filepath, as_attachment=True, download_name=safe_name)
