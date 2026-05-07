from app.web.routes.admin_routes import admin_bp
from app.web.routes.api_routes import api_bp
from app.web.routes.auth_routes import auth_bp
from app.web.routes.poll_routes import poll_bp
from app.web.routes.proposal_routes import proposal_bp


def register_blueprints(app):
    if app.extensions.get("manavote_blueprints_registered"):
        return

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(proposal_bp)
    app.register_blueprint(poll_bp)
    app.register_blueprint(admin_bp)

    legacy_endpoint_aliases = {
        "login": "auth.login",
        "logout": "auth.logout",
        "set_language": "auth.set_language",
        "change_password": "auth.change_password",
        "api_register": "api.api_register",
        "api_create_proposal": "api.api_create_proposal",
        "api_list_proposals": "api.api_list_proposals",
        "api_get_proposal": "api.api_get_proposal",
        "api_edit_proposal": "api.api_edit_proposal",
        "api_list_member_telegram_links": "api.api_list_member_telegram_links",
        "api_list_polls": "api.api_list_polls",
        "api_create_poll": "api.api_create_poll",
        "new_proposal": "proposals.new_proposal",
        "proposal_detail": "proposals.proposal_detail",
        "edit_comment": "proposals.edit_comment",
        "delete_comment": "proposals.delete_comment",
        "delete_proposal": "proposals.delete_proposal",
        "edit_proposal": "proposals.edit_proposal",
        "quick_vote": "proposals.quick_vote",
        "withdraw_vote": "proposals.withdraw_vote",
        "undo_approve": "proposals.undo_approve",
        "mark_purchased": "proposals.mark_purchased",
        "unmark_purchased": "proposals.unmark_purchased",
        "polls_page": "polls.polls_page",
        "admin": "admin.admin",
        "check_overbudget": "admin.check_overbudget",
    }
    for legacy_name, blueprint_name in legacy_endpoint_aliases.items():
        if legacy_name not in app.view_functions and blueprint_name in app.view_functions:
            app.view_functions[legacy_name] = app.view_functions[blueprint_name]

    app.extensions["manavote_blueprints_registered"] = True
