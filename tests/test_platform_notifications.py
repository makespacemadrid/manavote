"""Cross-transport delivery, durable deduplication and real 24-hour boundaries."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_mcp_copy import copy_db, call, payload
from app import app, mcp_server
from app.services import platform_notification_service as notices
from app.services import copy_service
from app.web.routes import main_routes


@pytest.fixture
def notification_db(copy_db, monkeypatch):
    path, uploads = copy_db
    def connect():
        conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; return conn
    monkeypatch.setattr(main_routes,'get_db',connect)
    monkeypatch.setattr(main_routes,'ADMIN_API_KEY','notice-api')
    monkeypatch.setitem(app.config,'WTF_CSRF_ENABLED',False)
    monkeypatch.setitem(app.config,'UPLOAD_FOLDER',str(uploads))
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','fake-notification-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID','-123')
    monkeypatch.setenv('TELEGRAM_THREAD_ID','9')
    client = Mock()
    for method in ['send_message','send_poll_message','send_proposal_vote_message']:
        getattr(client,method).return_value = True
    factory = Mock(return_value=client)
    monkeypatch.setattr(notices,'TelegramClient',factory)
    monkeypatch.setattr(main_routes,'send_telegram_message',Mock(return_value=True))
    monkeypatch.setattr(main_routes,'TelegramClient',Mock(return_value=client))
    monkeypatch.setattr(mcp_server,'TelegramClient',Mock(return_value=client))
    return path,connect,client,factory


@pytest.mark.parametrize('kind,method',[('proposal','send_proposal_vote_message'),('poll','send_poll_message'),('group_purchase','send_message')])
def test_fresh_copy_announces_and_replays_do_not(notification_db,kind,method):
    path,connect,client,factory = notification_db
    first = payload(call(kind,{'source_id':1,'created_by':2,'idempotency_key':'same'}))
    repeated = payload(call(kind,{'source_id':1,'created_by':2,'idempotency_key':'same'}))
    assert repeated['replayed'] and repeated[kind+'_id'] == first[kind+'_id']
    assert getattr(client,method).call_count == 1
    factory.assert_called_once_with('fake-notification-token','-123','9')
    with connect() as conn:
        assert conn.execute("SELECT status FROM platform_notifications").fetchone()[0] == 'sent'
    payload(call(kind,{'source_id':1,'created_by':2,'idempotency_key':'another'}))
    assert getattr(client,method).call_count == 2


@pytest.mark.parametrize('collection,kind',[('proposals','proposal'),('polls','poll'),('group-purchases','group_purchase')])
def test_rest_and_web_share_the_mcp_delivery_and_retry_key(notification_db,collection,kind):
    _,connect,client,_ = notification_db
    http = app.test_client()
    args = {'created_by':2,'idempotency_key':'cross-transport'}
    response = http.post(f'/api/{collection}/1/copy',json=args,headers={'X-Admin-Key':'notice-api'})
    assert response.status_code == 201
    new_id = response.json[kind+'_id']
    assert payload(call(kind,{'source_id':1,**args}))['replayed']
    with http.session_transaction() as session:
        session.update(member_id=2,username='requester',is_admin=True)
    response = http.post(f'/admin/copy/{kind}/1',data={'idempotency_key':'cross-transport'})
    assert response.status_code == 302
    assert sum(getattr(client,m).call_count for m in ['send_message','send_poll_message','send_proposal_vote_message']) == 1
    assert http.post(f'/api/{collection}/1/copy',json=args,headers={'X-Admin-Key':'notice-api'}).status_code == 200
    with connect() as conn:
        assert conn.execute('SELECT item_id FROM platform_notifications').fetchone()[0] == new_id


def seed_deadlines(connect):
    with connect() as conn:
        conn.execute("UPDATE proposals SET status='active',voting_deadline='2030-01-10T23:00:00' WHERE id=1")
        conn.execute("UPDATE polls SET status='open',closes_at='2030-01-10T23:00:00' WHERE id=1")
        conn.execute("UPDATE group_purchases SET status='open',deadline='2030-01-10' WHERE id=1")
    return datetime(2030,1,9,23,tzinfo=timezone.utc)


def test_reminders_enter_the_24h_window_once_across_restarts(notification_db):
    path,connect,client,_ = notification_db
    now = seed_deadlines(connect)
    notices.run_notifications(path,now=now-timedelta(seconds=1))
    client.send_message.assert_not_called()
    notices.run_notifications(path,now=now)
    assert client.send_message.call_count == 3
    messages = [call.args[0] for call in client.send_message.call_args_list]
    assert any('Joining' in text and '2030-01-11 00:00 CET' in text for text in messages)
    assert all('within 24 hours' in text for text in messages)
    notices.run_notifications(path,now=now+timedelta(minutes=1))
    assert client.send_message.call_count == 3


@pytest.mark.parametrize('mutation',[
    "UPDATE proposals SET status='approved'",
    "UPDATE polls SET status='closed'",
    "UPDATE group_purchases SET status='closed'",
])
def test_closed_items_are_not_warned(notification_db,mutation):
    path,connect,client,_ = notification_db
    now = seed_deadlines(connect)
    with connect() as conn: conn.execute(mutation)
    notices.run_notifications(path,now=now)
    assert client.send_message.call_count == 2


def test_overdue_items_and_invalid_dates_are_skipped(notification_db):
    path,connect,client,_ = notification_db
    now = seed_deadlines(connect)
    notices.run_notifications(path,now=now+timedelta(days=1))
    client.send_message.assert_not_called()
    with connect() as conn: conn.execute("UPDATE polls SET closes_at='nonsense'")
    notices.run_notifications(path,now=now+timedelta(days=1))
    client.send_message.assert_not_called()


def test_unconfigured_delivery_waits_but_stale_warnings_are_not_sent(notification_db,monkeypatch):
    path,connect,client,_ = notification_db
    now = seed_deadlines(connect)
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN')
    notices.run_notifications(path,now=now)
    client.send_message.assert_not_called()
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','restored')
    notices.run_notifications(path,now=now+timedelta(days=1))
    client.send_message.assert_not_called()
    with connect() as conn:
        assert {r[0] for r in conn.execute('SELECT status FROM platform_notifications')} == {'skipped'}


def test_transport_failure_keeps_copy_and_does_not_duplicate(notification_db):
    path,connect,client,_ = notification_db
    client.send_proposal_vote_message.side_effect = OSError('ambiguous transport failure')
    result = payload(call('proposal',{'source_id':1,'created_by':2}))
    assert result['success']
    notices.run_notifications(path)
    assert client.send_proposal_vote_message.call_count == 1
    with connect() as conn:
        assert conn.execute('SELECT status FROM platform_notifications').fetchone()[0] == 'failed'
        assert conn.execute('SELECT id FROM proposals WHERE id=?',(result['proposal_id'],)).fetchone()


@pytest.mark.parametrize('date_value,expected', [('2030-03-31','2030-03-31T22:00:00+00:00'),('2030-10-27','2030-10-27T23:00:00+00:00')])
def test_date_only_deadlines_follow_madrid_dst(date_value,expected):
    assert notices.deadline_instant('group_purchase',date_value,{}).isoformat() == expected


@pytest.mark.parametrize('kind,field,collection',[('proposal','voting_deadline','proposals'),('poll','closes_at','polls')])
def test_rest_and_mcp_creation_persist_deadlines(notification_db,kind,field,collection):
    _,connect,_,_ = notification_db
    data = {'title':'A future proposal','amount':10,'created_by':2} if kind=='proposal' else {'question':'A future poll?','options':['A','B'],'created_by':2}
    data[field]='2099-01-11T18:00:00+01:00'
    response=app.test_client().post('/api/'+collection,json=data,headers={'X-Admin-Key':'notice-api'})
    assert response.status_code == 201
    response=mcp_server.handle_request({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'api_key':'copy-test-key','name':'create_'+kind,'arguments':data}})
    assert 'error' not in response
    with connect() as conn:
        values=[r[0] for r in conn.execute(f'SELECT {field} FROM {collection} WHERE id>1')]
        assert values == ['2099-01-11T17:00:00']*2


def test_web_proposal_stores_local_deadline_in_utc(notification_db,monkeypatch):
    _,connect,_,_ = notification_db
    monkeypatch.setattr(main_routes,'process_proposal',Mock())
    http=app.test_client()
    with http.session_transaction() as session: session.update(member_id=2,username='requester')
    response=http.post('/proposal/new',data={'title':'Save my deadline','description':'Details','amount':'10','voting_deadline':'2099-01-11T18:00'})
    assert response.status_code == 302
    with connect() as conn:
        assert conn.execute('SELECT voting_deadline FROM proposals WHERE id>1').fetchone()[0] == '2099-01-11T17:00:00'


def test_rest_edit_changes_clears_and_exposes_deadline(notification_db):
    _,connect,_,_ = notification_db
    with connect() as conn: conn.execute("UPDATE proposals SET status='active' WHERE id=1")
    http=app.test_client(); headers={'X-Admin-Key':'notice-api'}
    assert http.patch('/api/proposals/1',json={'voting_deadline':'2099-01-11T18:00:00+01:00'},headers=headers).status_code == 200
    assert http.get('/api/proposals/1',headers=headers).json['proposal']['voting_deadline'] == '2099-01-11T17:00:00'
    assert http.patch('/api/proposals/1',json={'title':'Retain date'},headers=headers).status_code == 200
    with connect() as conn: assert conn.execute('SELECT voting_deadline FROM proposals WHERE id=1').fetchone()[0]
    assert http.patch('/api/proposals/1',json={'voting_deadline':None},headers=headers).status_code == 200
    with connect() as conn: assert conn.execute('SELECT voting_deadline FROM proposals WHERE id=1').fetchone()[0] is None


@pytest.mark.parametrize('kind',['proposal','poll','group_purchase'])
def test_fresh_web_copy_announces(notification_db,kind):
    _,_,client,_=notification_db
    http=app.test_client()
    with http.session_transaction() as session: session.update(member_id=2,username='requester',is_admin=True)
    response=http.post(f'/admin/copy/{kind}/1',data={'idempotency_key':'fresh-web'})
    assert response.status_code == 302
    assert sum(getattr(client,m).call_count for m in ['send_message','send_poll_message','send_proposal_vote_message']) == 1


def test_changed_deadline_receives_a_new_warning(notification_db):
    path,connect,client,_=notification_db
    now=seed_deadlines(connect)
    notices.run_notifications(path,now=now)
    with connect() as conn: conn.execute("UPDATE polls SET closes_at='2030-01-10T22:00:00'")
    notices.run_notifications(path,now=now)
    assert client.send_message.call_count == 4


def test_concurrent_workers_claim_one_delivery(notification_db):
    path,connect,client,_=notification_db
    with connect() as conn: notices.queue_copy(conn,'poll',1)
    def deliver():
        with connect() as conn: notices.deliver_pending(conn)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:deliver(),range(2)))
    assert client.send_poll_message.call_count == 1


def test_copy_deadline_override_and_auth_validation(notification_db):
    _,connect,client,_=notification_db
    http=app.test_client(); url='/api/proposals/1/copy'; headers={'X-Admin-Key':'notice-api'}
    assert http.post(url,json={'created_by':2}).status_code == 401
    for body in [{'created_by':True},{'created_by':2,'unrecognized':1},{'created_by':2,'deadline':'2099-01-01T12:00:00'}]:
        assert http.post(url,json=body,headers=headers).status_code == 400
    result=payload(call('proposal',{'source_id':1,'created_by':2,'deadline':'2099-01-11T18:00:00+01:00'}))
    with connect() as conn:
        assert conn.execute('SELECT voting_deadline FROM proposals WHERE id=?',(result['proposal_id'],)).fetchone()[0] == '2099-01-11T17:00:00'


@pytest.mark.parametrize('mode',['web_only','telegram_only','both'])
def test_copy_announcement_respects_telegram_voting_mode(notification_db,mode):
    _,connect,client,_=notification_db
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('proposal_vote_mode',?)",(mode,))
    payload(call('proposal',{'source_id':1,'created_by':2}))
    assert client.send_proposal_vote_message.call_count == (0 if mode=='web_only' else 1)
    assert client.send_message.call_count == (1 if mode=='web_only' else 0)


def test_notification_queue_and_copy_commit_atomically(notification_db,monkeypatch):
    _,connect,client,_=notification_db
    monkeypatch.setattr(copy_service,'queue_copy',Mock(side_effect=sqlite3.OperationalError('storage failure')))
    response=call('proposal',{'source_id':1,'created_by':2})
    assert response['error']['code'] == -32012
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM proposals').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM platform_notifications').fetchone()[0] == 0
    client.send_proposal_vote_message.assert_not_called()


def test_long_copy_announcements_fit_one_message(notification_db):
    _,connect,client,_=notification_db
    with connect() as conn: conn.execute('UPDATE proposals SET title=? WHERE id=1',('A'*5000,))
    result=payload(call('proposal',{'source_id':1,'created_by':2}))
    message=client.send_proposal_vote_message.call_args.args[0]
    assert len(message)<4096 and f"/proposal/{result['proposal_id']}" in message
