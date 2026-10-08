from contextlib import closing
import os
import secrets
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.services import proposal_actions_service
from app.services.budget_service import build_budget_page
from app.services.proposal_page_service import build_proposal_page, build_proposal_detail
from app.web.decorators import admin_required, login_required
from app.web.routes import main_routes as legacy

proposal_bp = Blueprint("proposals", __name__)


@proposal_bp.route("/about", endpoint="about")
def about():
    return render_template("about.html", session_lang=session.get("lang", "en"))


@proposal_bp.route("/budget", endpoint="budget")
def budget():
    if not session.get("member_id"):
        return redirect(url_for("auth.login"))

    conn = legacy.get_db()
    try:
        model = build_budget_page(
            conn,
            sort_by=request.args.get("sort", "date_desc"),
            page=request.args.get("page", 1, type=int),
        )
    finally:
        conn.close()
    return render_template("budget.html", **model, session_lang=session.get("lang", "en"))


@proposal_bp.route("/proposals", endpoint="proposals")
@login_required
def proposals():
    conn = legacy.get_db()
    try:
        model = build_proposal_page(
            conn,
            member_id=session["member_id"],
            filter_type=request.args.get("filter", "active"),
        )
    finally:
        conn.close()
    return render_template(
        "proposals.html",
        **model,
        session_lang=session.get("lang", "en"),
        is_web_proposal_vote_enabled=legacy.is_web_proposal_voting_enabled(),
        proposal_vote_mode=legacy.get_proposal_vote_mode(),
    )


@proposal_bp.route("/proposal/new", methods=["GET", "POST"], endpoint="new_proposal")
@login_required
def new_proposal():
    # Local aliases so the body below (relocated from the legacy main_routes module)
    # can reference these names unchanged; each is re-read from the legacy module on
    # every request rather than imported once, so module-level state and test
    # monkeypatches on main_routes still take effect.
    get_db = legacy.get_db
    get_base_url = legacy.get_base_url
    get_current_budget = legacy.get_current_budget
    get_thresholds = legacy.get_thresholds
    can_record_proposal_vote = legacy.can_record_proposal_vote
    process_proposal = legacy.process_proposal
    send_telegram_message = legacy.send_telegram_message
    detect_image_type = legacy.detect_image_type
    TelegramClient = legacy.TelegramClient
    TELEGRAM_BOT_TOKEN = legacy.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID = legacy.TELEGRAM_CHAT_ID
    TELEGRAM_THREAD_ID = legacy.TELEGRAM_THREAD_ID
    app = legacy.app

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        amount = float(request.form["amount"])
        url = request.form.get("url", "").strip()
        voting_deadline = request.form.get("voting_deadline", "").strip()
        basic_supplies = 1 if request.form.get("basic_supplies") else 0
        if amount <= 0:
            flash("Amount must be positive", "error")
            return redirect(url_for("proposals.new_proposal"))
        deadline_text = ""
        if voting_deadline:
            try:
                deadline_dt = datetime.fromisoformat(voting_deadline)
                deadline_text = deadline_dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                flash("Invalid voting deadline", "error")
                return redirect(url_for("proposals.new_proposal"))

        image_filename = None
        if "image" in request.files:
            image = request.files["image"]
            if image and image.filename:
                ext = image.filename.split(".")[-1].lower()
                if ext in ["jpg", "jpeg", "png"]:
                    image_filename = f"{secrets.token_hex(8)}.{ext}"
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    image.save(filepath)

                    mime_type = detect_image_type(filepath)
                    if mime_type not in ["jpeg", "png"]:
                        os.remove(filepath)
                        flash("Invalid image format", "error")
                        return redirect(url_for("proposals.new_proposal"))

        conn = get_db()
        try:
            proposal_id, creator = proposal_actions_service.create_web_proposal(
                conn, title=title, description=description, amount=amount, url=url,
                image_filename=image_filename, member_id=session["member_id"],
                basic_supplies=basic_supplies, process_proposal=process_proposal,
            )
        finally:
            conn.close()

        base_url = get_base_url()

        deadline_line = f"\n⏰ Vote by: {deadline_text}" if deadline_text else ""
        message = f"*{title}*\n\n🆕 New proposal\nBy: {creator.split('@')[0]}\nAmount: €{amount}{deadline_line}\n\n{description[:200]}{'...' if len(description) > 200 else ''}\n\n👉 {url if url else 'No link'}\n🔗 {base_url}/proposal/{proposal_id}"
        if can_record_proposal_vote("telegram"):
            TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID).send_proposal_vote_message(message, proposal_id)
        else:
            send_telegram_message(message)

        flash("Proposal created!", "success")
        return redirect(url_for("proposals"))

    current_budget = get_current_budget()
    thresholds = get_thresholds()
    return render_template(
        "new_proposal.html",
        current_budget=current_budget,
        thresholds=thresholds,
        session_lang=session.get("lang", "en"),
    )


@proposal_bp.route("/proposal/<int:proposal_id>", methods=["GET", "POST"], endpoint="proposal_detail")
@login_required
def proposal_detail(proposal_id):
    conn = legacy.get_db()
    try:
        model = build_proposal_detail(
            conn, proposal_id=proposal_id, member_id=session["member_id"],
            get_member_count=legacy.get_member_count, get_current_budget=legacy.get_current_budget,
            get_thresholds=legacy.get_thresholds, calculate_min_backers=legacy.calculate_min_backers,
            get_vote_counts=legacy.get_vote_counts,
        )
        if model is None:
            flash("Proposal not found", "error")
            return redirect(url_for("proposals"))
        if request.method == "POST":
            if "vote" in request.form:
                if not legacy.can_record_proposal_vote("web"):
                    legacy.log_proposal_vote_event(
                        event="proposal_vote_rejected", source="web", proposal_id=proposal_id,
                        member_id=session.get("member_id"), reason_code="channel_disabled",
                    )
                    flash("Web voting is disabled by admin", "error")
                else:
                    legacy.record_proposal_vote(proposal_id, session["member_id"], request.form["vote"], source="web")
                    flash("Vote recorded!", "success")
            elif "comment" in request.form:
                if proposal_actions_service.add_comment(conn, proposal_id=proposal_id,
                        member_id=session["member_id"], content=request.form["comment"]):
                    flash("Comment added!", "success")
            return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))
    finally:
        conn.close()
    return render_template(
        "proposal_detail.html", **model, session_lang=session.get("lang", "en"),
        is_web_proposal_vote_enabled=legacy.is_web_proposal_voting_enabled(),
        proposal_vote_mode=legacy.get_proposal_vote_mode(),
    )


@proposal_bp.route("/comment/<int:comment_id>/edit", methods=["GET", "POST"], endpoint="edit_comment")
@login_required
@admin_required
def edit_comment(comment_id):
    conn = legacy.get_db()
    try:
        comment = proposal_actions_service.get_comment_for_edit(
            conn, comment_id=comment_id, is_admin=session.get("is_admin")
        )
        if request.method == "POST":
            result = proposal_actions_service.update_comment(
                conn, comment_id=comment_id, member_id=session["member_id"],
                is_admin=session.get("is_admin"), content=request.form["content"],
            )
            if result["updated"]:
                flash("Comment updated!", "success")
            return redirect(url_for("proposals.proposal_detail", proposal_id=result["proposal_id"]))
    except proposal_actions_service.ProposalActionError as exc:
        flash("Admin access required" if exc.code == "admin_required" else "Comment not found", "error")
        return redirect(url_for("proposals"))
    finally:
        conn.close()
    return render_template("edit_comment.html", comment=comment, session_lang=session.get("lang", "en"))


@proposal_bp.route("/comment/<int:comment_id>/delete", methods=["POST"], endpoint="delete_comment")
@login_required
@admin_required
def delete_comment(comment_id):
    conn = legacy.get_db()
    try:
        proposal_id = proposal_actions_service.delete_comment(
            conn, comment_id=comment_id, member_id=session["member_id"], is_admin=session.get("is_admin")
        )
    except proposal_actions_service.ProposalActionError as exc:
        flash("Admin access required" if exc.code == "admin_required" else "Comment not found", "error")
        return redirect(url_for("proposals"))
    finally:
        conn.close()
    flash("Comment deleted!", "success")
    return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))


@proposal_bp.route("/proposal/<int:proposal_id>/delete", methods=["POST"], endpoint="delete_proposal")
@login_required
def delete_proposal(proposal_id):
    conn = legacy.get_db()
    try:
        proposal_actions_service.delete_proposal(
            conn, proposal_id=proposal_id, member_id=session["member_id"], is_admin=session.get("is_admin")
        )
    except proposal_actions_service.ProposalActionError as exc:
        messages = {
            "proposal_not_found": "Proposal not found",
            "proposal_processed": "Cannot delete processed proposals",
            "proposal_owner_required": "You can only delete your own proposals",
        }
        flash(messages[exc.code], "error")
        target = "proposals" if exc.code == "proposal_not_found" else "proposals.proposal_detail"
        return redirect(url_for(target, **({} if target == "proposals" else {"proposal_id": proposal_id})))
    finally:
        conn.close()
    flash("Proposal deleted!", "success")
    return redirect(url_for("proposals"))


@proposal_bp.route("/proposal/<int:proposal_id>/edit", methods=["GET", "POST"], endpoint="edit_proposal")
@login_required
def edit_proposal(proposal_id):
    get_db = legacy.get_db
    get_current_budget = legacy.get_current_budget
    get_thresholds = legacy.get_thresholds
    detect_image_type = legacy.detect_image_type
    app = legacy.app

    with closing(get_db()) as conn:
        try:
            proposal = proposal_actions_service.get_proposal_for_web_edit(
                conn, proposal_id=proposal_id, member_id=session["member_id"], is_admin=session.get("is_admin"),
            )
        except proposal_actions_service.ProposalActionError as exc:
            messages = {"proposal_not_found": "Proposal not found", "proposal_owner_required": "You can only edit your own proposals", "proposal_processed": "Cannot edit processed proposals"}
            flash(messages[exc.code], "error")
            return redirect(url_for("proposals"))

        if request.method == "POST":
            title = request.form["title"]
            description = request.form["description"]
            amount = float(request.form["amount"])
            url = request.form.get("url", "").strip()
            basic_supplies = 1 if request.form.get("basic_supplies") else 0
            if amount <= 0:
                flash("Amount must be positive", "error")
                return redirect(url_for("proposals.edit_proposal", proposal_id=proposal_id))

            image_filename = proposal["image_filename"]
            if "image" in request.files:
                image = request.files["image"]
                if image and image.filename:
                    ext = image.filename.split(".")[-1].lower()
                    if ext in ["jpg", "jpeg", "png"]:
                        if image_filename and os.path.exists(
                            os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                        ):
                            os.remove(
                                os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                            )
                        image_filename = f"{secrets.token_hex(8)}.{ext}"
                        filepath = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                        image.save(filepath)

                        mime_type = detect_image_type(filepath)
                        if mime_type not in ["jpeg", "png"]:
                            os.remove(filepath)
                            flash("Invalid image format", "error")
                            return redirect(
                                url_for("proposals.edit_proposal", proposal_id=proposal_id)
                            )

            proposal_actions_service.update_web_proposal(
                conn, proposal_id=proposal_id, member_id=session["member_id"], is_admin=session.get("is_admin"),
                title=title, description=description, amount=amount, url=url,
                image_filename=image_filename, basic_supplies=basic_supplies,
            )

            flash("Proposal updated!", "success")
            return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))

        current_budget = get_current_budget()
        thresholds = get_thresholds()
        return render_template(
            "edit_proposal.html",
            proposal=proposal,
            current_budget=current_budget,
            thresholds=thresholds,
            session_lang=session.get("lang", "en"),
        )


@proposal_bp.route("/vote/<int:proposal_id>", methods=["POST"], endpoint="quick_vote")
@login_required
def quick_vote(proposal_id):
    can_record_proposal_vote = legacy.can_record_proposal_vote
    record_proposal_vote = legacy.record_proposal_vote

    if not can_record_proposal_vote("web"):
        legacy.log_proposal_vote_event(
            event="proposal_vote_rejected",
            source="web",
            proposal_id=proposal_id,
            member_id=session.get("member_id"),
            reason_code="channel_disabled",
        )
        flash("Web voting is disabled by admin", "error")
        return redirect(url_for("proposals"))

    vote = request.form.get("vote")
    record_proposal_vote(proposal_id, session["member_id"], vote, source="web")
    flash("Vote recorded!", "success")
    return redirect(url_for("proposals"))


@proposal_bp.route("/withdraw-vote/<int:proposal_id>", methods=["POST"], endpoint="withdraw_vote")
@login_required
def withdraw_vote(proposal_id):
    conn = legacy.get_db()
    try:
        proposal_actions_service.withdraw_vote(
            conn, proposal_id=proposal_id, member_id=session["member_id"],
            process_proposal=legacy.process_proposal,
        )
    except proposal_actions_service.ProposalActionError:
        flash("Cannot withdraw vote on processed proposals", "error")
        return redirect(url_for("proposals"))
    finally:
        conn.close()
    flash("Vote withdrawn!", "success")
    return redirect(url_for("proposals"))


@proposal_bp.route("/undo/<int:proposal_id>", methods=["POST"], endpoint="undo_approve")
@login_required
@admin_required
def undo_approve(proposal_id):
    conn = legacy.get_db()
    try:
        restored = proposal_actions_service.undo_approval(
            conn, proposal_id=proposal_id, member_id=session["member_id"],
            is_admin=session.get("is_admin", False),
            process_proposal=legacy.process_proposal,
            check_over_budget_proposals=legacy.check_over_budget_proposals,
        )
    finally:
        conn.close()
    if restored:
        flash("Approval undone, budget restored", "success")
    return redirect(url_for("proposals"))


def _purchase_response(proposal_id, *, purchased):
    conn = legacy.get_db()
    try:
        proposal_actions_service.set_purchase_state(
            conn, proposal_id=proposal_id, member_id=session["member_id"], purchased=purchased
        )
    except proposal_actions_service.ProposalActionError as exc:
        if exc.code == "proposal_not_approved" and purchased:
            flash("Can only mark approved proposals as purchased", "error")
            return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))
        flash("Proposal not found", "error")
        return redirect(url_for("proposals"))
    finally:
        conn.close()
    flash("Marked as purchased!" if purchased else "Purchase status removed", "success")
    return redirect(url_for("proposals.proposal_detail", proposal_id=proposal_id))


@proposal_bp.route("/purchase/<int:proposal_id>", methods=["POST"], endpoint="mark_purchased")
@login_required
def mark_purchased(proposal_id):
    return _purchase_response(proposal_id, purchased=True)


@proposal_bp.route("/unpurchase/<int:proposal_id>", methods=["POST"], endpoint="unmark_purchased")
@login_required
def unmark_purchased(proposal_id):
    return _purchase_response(proposal_id, purchased=False)
