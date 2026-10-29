"""Opt-in private Telegram delivery; durable in-app notices are always retained."""
import logging
import os
import sqlite3

from app.db.transactions import write_transaction
from app.integrations.telegram_client import TelegramClient
from app.repositories.feedback_repo import FeedbackRepository

logger = logging.getLogger(__name__)


def set_preferences(conn, member_id, enabled, language):
    repo = FeedbackRepository(conn)
    member = repo.member(member_id)
    if member is None or (enabled and not member['telegram_user_id']):
        raise ValueError('Link your Telegram account before enabling notifications.')
    with write_transaction(conn):
        repo.preferences(member_id, enabled, 'es' if language == 'es' else 'en')


def deliver_resolution(conn, notification_id):
    repo = FeedbackRepository(conn)
    try:
        with write_transaction(conn):
            notice = repo.delivery(notification_id)
            if notice is None:
                return
            member = repo.member(notice['member_id'])
            token = os.getenv('TELEGRAM_BOT_TOKEN', '')
            enabled = member is not None and 'feedback_telegram_notifications' in member.keys() and member['feedback_telegram_notifications']
            if not token or not enabled or not member['telegram_user_id']:
                return
            if not repo.claim_delivery(notification_id):
                return
            chat_id = str(member['telegram_user_id'])
            language = member['feedback_notification_language']
        # Do not hold a SQLite writer during the network request. Recheck preferences/link.
        member = repo.member(notice['member_id'])
        if not member or not member['feedback_telegram_notifications'] or str(member['telegram_user_id']) != chat_id:
            sent = False
        else:
            text = 'Tu comentario se ha resuelto' if language == 'es' else 'Your feedback was resolved'
            try:
                sent = TelegramClient(token, chat_id).send_message(f'✅ {text} #{notice["feedback_id"]}.')
            except (OSError, ValueError, RuntimeError, TypeError, AttributeError):
                sent = False
        with write_transaction(conn):
            repo.finish_delivery(notification_id, 'sent' if sent else 'failed')
        logger.log(logging.INFO if sent else logging.WARNING,
            'event=feedback_telegram_delivery notification_id=%s status=%s', notification_id, 'sent' if sent else 'failed')
    except sqlite3.Error:
        # Resolving feedback already committed; diagnostic failure cannot undo it.
        logger.warning('event=feedback_telegram_delivery notification_id=%s status=storage_unavailable', notification_id)
