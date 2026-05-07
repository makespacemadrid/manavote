from flask import Blueprint

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

poll_bp = Blueprint("polls", __name__)


@poll_bp.route("/polls", methods=["GET", "POST"], endpoint="polls_page")
@login_required
def polls_page():
    return legacy.polls_page()
