from unittest.mock import Mock
import sqlite3

import pytest

from app.db.initialization import initialize_database
from app.services import feedback_service
from app.services import feedback_notification_service as delivery


@pytest.fixture
def notifications_db(tmp_path):
    path=tmp_path/'feedback-telegram.db'
    initialize_database(str(path), testing=True, production=False, logger=Mock())
    conn=sqlite3.connect(path); conn.row_factory=sqlite3.Row
    conn.execute("INSERT INTO members(id,username,password_hash,telegram_user_id) VALUES (2,'member','unused',777)")
    conn.commit()
    yield conn
    conn.close()


def test_opt_in_telegram_resolutions_are_private_localized_and_not_duplicated(notifications_db, monkeypatch):
    conn=notifications_db
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','fake-token')
    sender=Mock(return_value=True)
    factory=Mock(return_value=Mock(send_message=sender))
    monkeypatch.setattr(delivery,'TelegramClient',factory)
    delivery.set_preferences(conn,2,True,'es')
    feedback_id=feedback_service.submit_feedback(conn,member_id=2,source='web',category='bug',message='private feedback contents')
    feedback_service.update_feedback_status(conn,feedback_id=feedback_id,status='resolved',resolved_by=1)
    feedback_service.update_feedback_status(conn,feedback_id=feedback_id,status='resolved',resolved_by=1)
    factory.assert_called_once_with('fake-token','777')
    sender.assert_called_once()
    text=sender.call_args.args[0]
    assert 'resuelto' in text and 'private feedback' not in text
    notice=conn.execute('SELECT * FROM feedback_notifications').fetchone()
    assert notice['telegram_status'] == 'sent' and notice['telegram_sent_at']
    delivery.deliver_resolution(conn,notice['id'])
    sender.assert_called_once()
    assert conn.execute('SELECT COUNT(*) FROM feedback_notifications').fetchone()[0] == 1


@pytest.mark.parametrize('scenario',['opted-out','unlinked','failed'])
def test_telegram_failure_or_unavailable_link_keeps_web_notice(notifications_db, monkeypatch, scenario):
    conn=notifications_db
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','fake-token')
    sender=Mock(return_value=False)
    monkeypatch.setattr(delivery,'TelegramClient',Mock(return_value=Mock(send_message=sender)))
    if scenario != 'opted-out': delivery.set_preferences(conn,2,True,'en')
    if scenario == 'unlinked':
        conn.execute('UPDATE members SET telegram_user_id=NULL WHERE id=2'); conn.commit()
    feedback_id=feedback_service.submit_feedback(conn,member_id=2,source='web',category='bug',message='fixture')
    feedback_service.update_feedback_status(conn,feedback_id=feedback_id,status='resolved',resolved_by=1)
    assert conn.execute('SELECT status FROM feedback WHERE id=?',(feedback_id,)).fetchone()[0] == 'resolved'
    assert conn.execute('SELECT COUNT(*) FROM feedback_notifications WHERE read_at IS NULL').fetchone()[0] == 1
    assert sender.call_count == (1 if scenario == 'failed' else 0)


def test_notification_opt_in_requires_link(notifications_db):
    conn=notifications_db
    with pytest.raises(ValueError,match='Link your Telegram'):
        delivery.set_preferences(conn,1,True,'en')
    delivery.set_preferences(conn,2,False,'en')
    assert conn.execute('SELECT feedback_telegram_notifications FROM members WHERE id=2').fetchone()[0] == 0
