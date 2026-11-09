"""Participant handoffs stay separate from shipment receipt, money and Telegram."""
import json
import sqlite3
from unittest.mock import patch

import pytest
from test_group_purchases import group_purchase_client
from app import mcp_server
from app import app
from app.db.migrations import run_migrations
from app.services.copy_service import copy_item
from app.services import group_purchase_service as service
from app.repositories.group_purchase_repo import GroupPurchaseRepository
from app.web.routes import main_routes


@pytest.fixture
def deliveries(group_purchase_client):
    client,path=group_purchase_client
    with sqlite3.connect(path) as conn:
        conn.executemany("INSERT INTO members(id,username,password_hash,is_admin) VALUES (?,?,'unused',?)",[(2,'participant',0),(3,'other-admin',1)])
        conn.execute("INSERT INTO group_purchases(id,title,created_by,status,deadline) VALUES (1,'Parts order',1,'received','2099-01-01')")
        conn.execute("INSERT INTO group_purchase_components(id,group_purchase_id,name,unit_price) VALUES (1,1,'Connectors',3)")
        conn.executemany('INSERT INTO group_purchase_quantities(component_id,member_id,quantity) VALUES (1,?,?)',[(1,2),(2,1)])
    return client,path


@pytest.mark.parametrize('language,mark,undo',[('en','Mark delivered','Undo delivery'),('es','Marcar entregado','Deshacer entrega')])
def test_organizer_marks_and_undoes_each_delivery_without_notifications(deliveries,language,mark,undo):
    client,path=deliveries
    with client.session_transaction() as session:session['lang']=language
    before=client.get('/group-purchases').get_data(as_text=True)
    assert mark in before
    with patch.object(main_routes,'send_telegram_message') as telegram:
        response=client.post('/group-purchases/1/deliveries/2',data={'delivered':'1'},follow_redirects=True)
        assert response.status_code==200
        assert undo in response.get_data(as_text=True)
        assert '1 / 2' in response.get_data(as_text=True)
        with sqlite3.connect(path) as conn:
            first=conn.execute('SELECT delivered_at,delivered_by FROM group_purchase_deliveries WHERE member_id=2').fetchone()
            assert first[0] and first[1]==1
            # A retry must preserve a genuinely older timestamp, not just the same second.
            conn.execute("UPDATE group_purchase_deliveries SET delivered_at='2000-01-01 12:00:00' WHERE member_id=2")
            first=('2000-01-01 12:00:00',1)
            assert conn.execute('SELECT COUNT(*) FROM group_purchase_payments').fetchone()[0]==0
        # Repeating a mark preserves the original handoff and never duplicates it.
        client.post('/group-purchases/1/deliveries/2',data={'delivered':'1'})
        with sqlite3.connect(path) as conn:
            assert conn.execute('SELECT delivered_at,delivered_by FROM group_purchase_deliveries WHERE member_id=2').fetchone()==first
            assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==1
        client.post('/group-purchases/1/payments/2',data={'received':'1'})
        client.post('/group-purchases/1/deliveries/2',data={'delivered':'0'})
        with sqlite3.connect(path) as conn:
            assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0
            assert conn.execute('SELECT COUNT(*) FROM group_purchase_payments WHERE member_id=2').fetchone()[0]==1
            assert conn.execute('SELECT status FROM group_purchases WHERE id=1').fetchone()[0]=='received'
        telegram.assert_not_called()


@pytest.mark.parametrize('actor,status,member,value',[
    (2,'received',2,'1'), (3,'received',2,'1'), (1,'open',2,'1'),
    (1,'closed',2,'1'), (1,'ordered',2,'1'), (1,'received',3,'1'),
    (1,'received',999,'1'), (1,'received',2,'invalid'), (1,'received',2,None),
])
def test_invalid_handoffs_cannot_mutate_delivery_state(deliveries,actor,status,member,value):
    client,path=deliveries
    with sqlite3.connect(path) as conn:conn.execute('UPDATE group_purchases SET status=?',(status,))
    with client.session_transaction() as session:session.update(member_id=actor,is_admin=actor in {1,3})
    with patch.object(main_routes,'send_telegram_message') as telegram:
        client.post(f'/group-purchases/1/deliveries/{member}',data={} if value is None else {'delivered':value})
        telegram.assert_not_called()
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0
    if actor!=1:
        assert '/deliveries/' not in client.get('/group-purchases').get_data(as_text=True)


def test_missing_purchase_and_login_are_guarded(deliveries):
    client,path=deliveries
    client.post('/group-purchases/999/deliveries/2',data={'delivered':'1'})
    with client.session_transaction() as session:session.clear()
    assert client.post('/group-purchases/1/deliveries/2',data={'delivered':'1'}).status_code==302
    with sqlite3.connect(path) as conn:assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0


def test_deliveries_are_readable_in_mcp_and_cleaned_up_on_delete(deliveries,monkeypatch):
    client,path=deliveries
    client.post('/group-purchases/1/deliveries/2',data={'delivered':'1'})
    monkeypatch.setattr(mcp_server,'DB_PATH',str(path))
    response=mcp_server.execute_tool_command('list_group_purchases',{})
    data=json.loads(response['result']['content'][0]['text'])
    purchase=data['group_purchases'][0]
    assert purchase['delivered_participant_count']==1
    assert next(p for p in purchase['participants'] if p['member_id']==2)['delivered_at']
    with sqlite3.connect(path) as conn:
        GroupPurchaseRepository(conn).delete(1)
        assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0


@pytest.mark.parametrize('language,placed,received', [('en','Order placed','Shipment received'),('es','Pedido realizado','Envío recibido')])
def test_status_notifications_omit_the_joining_deadline(deliveries,language,placed,received):
    client,path=deliveries
    with sqlite3.connect(path) as conn:conn.execute("UPDATE group_purchases SET status='closed'")
    with client.session_transaction() as session:session['lang']=language
    with patch.object(main_routes,'send_telegram_message',return_value=True) as telegram:
        client.post('/group-purchases/1/status',data={'status':'ordered'})
        client.post('/group-purchases/1/status',data={'status':'received'})
        messages=[call.args[0] for call in telegram.call_args_list]
        assert len(messages)==2 and placed in messages[0] and received in messages[1]
        assert all('2099-01-01' not in text and '📅' not in text for text in messages)
        assert all('Parts order' in text for text in messages)


def test_delivery_write_rolls_back_on_failure(deliveries,monkeypatch):
    _,path=deliveries
    conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row
    original=GroupPurchaseRepository.set_delivery
    def fail(repo,*args):
        original(repo,*args)
        raise sqlite3.OperationalError('simulated failure')
    monkeypatch.setattr(GroupPurchaseRepository,'set_delivery',fail)
    with pytest.raises(sqlite3.OperationalError):
        service.update_delivery(conn,purchase_id=1,member_id=2,actor_id=1,delivered=True)
    assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0
    conn.close()


def test_delivery_post_requires_csrf(deliveries,monkeypatch):
    client,path=deliveries
    monkeypatch.setitem(app.config,'WTF_CSRF_ENABLED',True)
    assert client.post('/group-purchases/1/deliveries/2',data={'delivered':'1'}).status_code==400
    with sqlite3.connect(path) as conn:assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0


def test_upgrade_is_idempotent_and_does_not_mark_old_shipments_delivered(deliveries):
    client,path=deliveries
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO group_purchase_payments(group_purchase_id,member_id) VALUES (1,2)')
        conn.execute('DROP TABLE group_purchase_deliveries')
        run_migrations(conn.cursor());run_migrations(conn.cursor())
        assert conn.execute('SELECT COUNT(*) FROM group_purchase_payments').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0
    assert b'Awaiting collection' in client.get('/group-purchases').data


def test_copy_starts_without_deliveries(deliveries):
    client,path=deliveries
    client.post('/group-purchases/1/deliveries/2',data={'delivered':'1'})
    conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row
    with patch('app.services.copy_service.deliver_pending'):
        copied=copy_item(conn,kind='group_purchase',source_id=1,created_by=1,upload_folder=app.config['UPLOAD_FOLDER'])
    assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries WHERE group_purchase_id=?',(copied['group_purchase_id'],)).fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries WHERE group_purchase_id=1').fetchone()[0]==1
    conn.close()


def test_zero_quantity_is_not_a_delivery_participant(deliveries):
    client,path=deliveries
    with sqlite3.connect(path) as conn:conn.execute('UPDATE group_purchase_quantities SET quantity=0 WHERE member_id=2')
    client.post('/group-purchases/1/deliveries/2',data={'delivered':'1'})
    with sqlite3.connect(path) as conn:assert conn.execute('SELECT COUNT(*) FROM group_purchase_deliveries').fetchone()[0]==0
