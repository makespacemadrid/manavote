"""Authenticated MCP copy contracts and clean-state/transaction guarantees."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app import mcp_server
from app.db.initialization import initialize_database
from app.services.mcp_application import Actor, ToolAccessDenied, execute_tool
from app.services.mcp_tool_registry import telegram_tool_definitions


@pytest.fixture
def copy_db(tmp_path, monkeypatch):
    path = tmp_path / 'copy.db'
    initialize_database(str(path), testing=True, production=False, logger=Mock())
    uploads = tmp_path / 'uploads'; uploads.mkdir()
    (uploads / 'original.png').write_bytes(b'\x89PNG\r\n\x1a\nsource')
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO members(id,username,password_hash) VALUES (2,'requester','unused')")
    conn.execute("INSERT INTO proposals(id,title,description,amount,url,image_filename,created_by,status,processed_at,purchased_at) VALUES (1,'Old proposal','Details',40,'https://example.org','original.png',1,'approved','2000-01-01','2000-01-02')")
    conn.execute("INSERT INTO votes(proposal_id,member_id,vote) VALUES (1,1,'in_favor')")
    conn.execute("INSERT INTO comments(proposal_id,member_id,content) VALUES (1,1,'old discussion')")
    conn.execute("INSERT INTO polls(id,question,options_json,created_by,status,closes_at,allow_multiple) VALUES (1,'Old poll question','[\"A\",\"B\"]',1,'closed','2000-01-01',1)")
    conn.execute("INSERT INTO poll_votes(poll_id,member_id,option_index) VALUES (1,1,0)")
    conn.execute("INSERT INTO group_purchases(id,title,description,created_by,status,deadline,url,image_filename,payment_method,join_member_limit,cap_at_125) VALUES (1,'Old order','Order description',1,'received','2000-01-01','https://example.org','original.png','Cash',3,1)")
    conn.execute("INSERT INTO group_purchase_components(id,group_purchase_id,name,unit_price,position) VALUES (1,1,'Part',10,0)")
    conn.execute("INSERT INTO group_purchase_shared_costs(group_purchase_id,label,amount) VALUES (1,'Shipping',5)")
    conn.execute("INSERT INTO group_purchase_quantities(component_id,member_id,quantity) VALUES (1,1,4)")
    conn.execute("INSERT INTO group_purchase_payments(group_purchase_id,member_id) VALUES (1,1)")
    conn.commit(); conn.close()
    monkeypatch.setattr(mcp_server, 'DB_PATH', str(path))
    monkeypatch.setattr(mcp_server, 'UPLOAD_FOLDER', str(uploads))
    monkeypatch.setattr(mcp_server, 'MCP_API_KEY', 'copy-test-key')
    return path, uploads


def call(kind, arguments, key='copy-test-key'):
    return mcp_server.handle_request({'jsonrpc':'2.0','id':12,'method':'tools/call',
        'params':{'api_key':key,'name':'copy_'+kind,'arguments':arguments}})


def payload(response):
    return json.loads(response['result']['content'][0]['text'])


@pytest.mark.parametrize('kind,table', [('proposal','proposals'),('poll','polls'),('group_purchase','group_purchases')])
def test_copy_creates_new_item_without_lifecycle_or_participation(copy_db, kind, table):
    path, uploads = copy_db
    with sqlite3.connect(path) as conn:
        before = conn.execute(f'SELECT * FROM {table} WHERE id=1').fetchone()
    result = payload(call(kind, {'source_id':1, 'created_by':2}))
    new_id = result[kind+'_id']
    assert result['success'] and new_id != 1
    conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
    copied = conn.execute(f'SELECT * FROM {table} WHERE id=?', (new_id,)).fetchone()
    assert copied['created_by'] == 2
    assert copied['status'] == ('active' if kind == 'proposal' else 'open')
    assert tuple(conn.execute(f'SELECT * FROM {table} WHERE id=1').fetchone()) == before
    if kind == 'proposal':
        assert copied['title'] == 'Old proposal' and copied['amount'] == 40
        assert copied['processed_at'] is None and copied['purchased_at'] is None
        assert conn.execute('SELECT COUNT(*) FROM votes WHERE proposal_id=?',(new_id,)).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM comments WHERE proposal_id=?',(new_id,)).fetchone()[0] == 0
    elif kind == 'poll':
        assert json.loads(copied['options_json']) == ['A','B'] and copied['allow_multiple'] == 1
        assert copied['closes_at'] is None
        assert conn.execute('SELECT COUNT(*) FROM poll_votes WHERE poll_id=?',(new_id,)).fetchone()[0] == 0
    else:
        assert copied['deadline'] is None and copied['payment_method'] == 'Cash'
        assert copied['cap_at_125'] == 1 and copied['join_member_limit'] == 3
        component = conn.execute('SELECT * FROM group_purchase_components WHERE group_purchase_id=?',(new_id,)).fetchone()
        assert component['id'] != 1 and component['name'] == 'Part' and component['unit_price'] == 10
        assert conn.execute('SELECT COUNT(*) FROM group_purchase_quantities WHERE component_id=?',(component['id'],)).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM group_purchase_payments WHERE group_purchase_id=?',(new_id,)).fetchone()[0] == 0
        assert conn.execute('SELECT amount FROM group_purchase_shared_costs WHERE group_purchase_id=?',(new_id,)).fetchone()[0] == 5
    if kind != 'poll':
        assert copied['image_filename'] != 'original.png'
        assert (uploads / copied['image_filename']).read_bytes() == (uploads/'original.png').read_bytes()
    conn.close()


@pytest.mark.parametrize('kind', ['proposal','poll','group_purchase'])
@pytest.mark.parametrize('arguments', [{'source_id':True,'created_by':2}, {'source_id':1,'created_by':True}, {'source_id':1}, {'source_id':0,'created_by':2}, {'source_id':1,'created_by':2,'status':'approved'}])
def test_copy_rejects_invalid_arguments_without_writes(copy_db, kind, arguments):
    assert call(kind, arguments)['error']['code'] == -32602
    assert len(list(copy_db[1].iterdir())) == 1


@pytest.mark.parametrize('kind', ['proposal','poll','group_purchase'])
def test_copy_not_found_and_authentication(copy_db, kind):
    assert call(kind, {'source_id':999,'created_by':2})['error']['code'] == -32004
    assert call(kind, {'source_id':1,'created_by':999})['error']['code'] == -32004
    assert call(kind, {'source_id':1,'created_by':2}, key='wrong')['error']['code'] == -32001


@pytest.mark.parametrize('kind', ['poll','group_purchase'])
def test_copy_resets_old_deadlines_and_accepts_new_names_and_deadlines(copy_db, kind):
    deadline = (datetime.now(timezone.utc)+timedelta(days=2))
    arguments = {'source_id':1,'created_by':2, 'question' if kind=='poll' else 'title':'New item for next week',
                 'deadline':deadline.isoformat() if kind=='poll' else deadline.date().isoformat()}
    result = payload(call(kind, arguments))
    with sqlite3.connect(copy_db[0]) as conn:
        column = 'closes_at' if kind=='poll' else 'deadline'
        table = 'polls' if kind=='poll' else 'group_purchases'
        expected = deadline.replace(tzinfo=None).isoformat() if kind == 'poll' else arguments['deadline']
        assert conn.execute(f'SELECT {column} FROM {table} WHERE id=?',(result[kind+'_id'],)).fetchone()[0] == expected
    arguments['deadline'] = '2000-01-01'
    assert call(kind, arguments)['error']['code'] == -32602


@pytest.mark.parametrize('kind,table', [('proposal','proposals'),('group_purchase','group_purchase_shared_costs')])
def test_failed_copy_rolls_back_and_removes_only_new_upload(copy_db, kind, table):
    path, uploads = copy_db
    with sqlite3.connect(path) as conn:
        conn.execute(f"CREATE TRIGGER stop_copy BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    assert call(kind, {'source_id':1,'created_by':2})['error']['code'] == -32012
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM proposals').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM group_purchases').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM group_purchase_components').fetchone()[0] == 1
    assert [p.name for p in uploads.iterdir()] == ['original.png']


@pytest.mark.parametrize('kind', ['proposal','poll','group_purchase'])
def test_copy_tools_are_confirmed_admin_writes_with_bound_creator(copy_db, kind):
    name = 'copy_'+kind
    definitions = mcp_server.tool_definitions()
    assert name not in {tool['name'] for tool in telegram_tool_definitions(definitions,is_admin=False,actor_member_id=2)}
    tool = next(tool for tool in telegram_tool_definitions(definitions,is_admin=True,actor_member_id=2) if tool['name']==name)
    assert tool['telegram_policy'] == 'confirmed_admin_write'
    assert 'created_by' not in tool['inputSchema']['properties']
    with pytest.raises(ToolAccessDenied):
        execute_tool(mcp_server.execute_tool_command,name,{'source_id':1,'created_by':1},actor=Actor('member',2))
    result = execute_tool(mcp_server.execute_tool_command,name,{'source_id':1,'created_by':1},actor=Actor('admin',2))
    new_id = payload(result)[kind+'_id']
    with sqlite3.connect(copy_db[0]) as conn:
        table = {'proposal':'proposals','poll':'polls','group_purchase':'group_purchases'}[kind]
        assert conn.execute(f'SELECT created_by FROM {table} WHERE id=?',(new_id,)).fetchone()[0] == 2
