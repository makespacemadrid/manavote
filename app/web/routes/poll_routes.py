from contextlib import closing

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.services import poll_service, poll_page_service
from app.web.decorators import login_required
from app.web.routes import main_routes as legacy

poll_bp = Blueprint('polls', __name__)


@poll_bp.route('/polls', methods=['GET', 'POST'], endpoint='polls_page')
@login_required
def polls_page():
    legacy.ensure_db_ready()
    with closing(legacy.get_db()) as conn:
        expired_poll_ids = legacy.close_expired_polls(conn)
        for expired_poll_id in expired_poll_ids:
            message = legacy.build_poll_results_message(conn, expired_poll_id)
            if message:
                legacy.send_telegram_message(message)
        if request.method == 'POST':
            poll_id = request.form.get('poll_id', type=int)
            if not legacy.is_web_poll_voting_enabled():
                poll_service.log_poll_vote_event(
                    legacy.app.logger, legacy.get_setting_value, event='poll_vote_rejected',
                    source='web', poll_id=poll_id, member_id=session.get('member_id'),
                    reason_code='channel_disabled',
                )
                flash('Web voting is disabled by admin', 'error')
                return redirect(url_for('polls.polls_page'))
            message = poll_page_service.vote_on_page(
                conn, poll_id=poll_id, member_id=session['member_id'],
                clear_vote=request.form.get('clear_vote') == '1',
                option_indexes=request.form.getlist('option_index'),
                single_index=request.form.get('option_index', type=int), logger=legacy.app.logger,
            )
            if message:
                flash(*message)
        context, messages = poll_page_service.build_poll_page(conn, member_id=session['member_id'], logger=legacy.app.logger)
    for message in messages:
        flash(*message)
    return render_template(
        'polls.html', **context, session_lang=session.get('lang', 'en'),
        is_telegram_vote_enabled=legacy.is_telegram_poll_voting_enabled(),
        is_web_vote_enabled=legacy.is_web_poll_voting_enabled(),
    )
