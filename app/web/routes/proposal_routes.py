from flask import Blueprint

from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

proposal_bp = Blueprint("proposals", __name__)


@proposal_bp.route("/proposal/new", methods=["GET", "POST"], endpoint="new_proposal")
@login_required
def new_proposal():
    return legacy.new_proposal()


@proposal_bp.route("/proposal/<int:proposal_id>", methods=["GET", "POST"], endpoint="proposal_detail")
@login_required
def proposal_detail(proposal_id):
    return legacy.proposal_detail(proposal_id)


@proposal_bp.route("/comment/<int:comment_id>/edit", methods=["GET", "POST"], endpoint="edit_comment")
@login_required
def edit_comment(comment_id):
    return legacy.edit_comment(comment_id)


@proposal_bp.route("/comment/<int:comment_id>/delete", methods=["POST"], endpoint="delete_comment")
@login_required
def delete_comment(comment_id):
    return legacy.delete_comment(comment_id)


@proposal_bp.route("/proposal/<int:proposal_id>/delete", methods=["POST"], endpoint="delete_proposal")
@login_required
def delete_proposal(proposal_id):
    return legacy.delete_proposal(proposal_id)


@proposal_bp.route("/proposal/<int:proposal_id>/edit", methods=["GET", "POST"], endpoint="edit_proposal")
@login_required
def edit_proposal(proposal_id):
    return legacy.edit_proposal(proposal_id)


@proposal_bp.route("/vote/<int:proposal_id>", methods=["POST"], endpoint="quick_vote")
@login_required
def quick_vote(proposal_id):
    return legacy.quick_vote(proposal_id)


@proposal_bp.route("/withdraw-vote/<int:proposal_id>", methods=["GET", "POST"], endpoint="withdraw_vote")
@login_required
def withdraw_vote(proposal_id):
    return legacy.withdraw_vote(proposal_id)


@proposal_bp.route("/undo/<int:proposal_id>", endpoint="undo_approve")
@login_required
def undo_approve(proposal_id):
    return legacy.undo_approve(proposal_id)


@proposal_bp.route("/purchase/<int:proposal_id>", methods=["POST"], endpoint="mark_purchased")
@login_required
def mark_purchased(proposal_id):
    return legacy.mark_purchased(proposal_id)


@proposal_bp.route("/unpurchase/<int:proposal_id>", methods=["POST"], endpoint="unmark_purchased")
@login_required
def unmark_purchased(proposal_id):
    return legacy.unmark_purchased(proposal_id)
