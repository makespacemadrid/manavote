from flask import Blueprint

from app.extensions import limiter

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin", methods=["GET", "POST"], endpoint="admin")
@limiter.exempt
@login_required
def admin():
    return legacy.admin()


@admin_bp.route("/check-overbudget", endpoint="check_overbudget")
@login_required
def check_overbudget():
    return legacy.check_overbudget()
