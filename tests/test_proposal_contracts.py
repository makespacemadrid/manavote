"""Independent public proposal contracts: shared facts, distinct wire shapes."""
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from app import app, mcp_server
from app.db.migrations import run_migrations
from app.services.proposal_service import ProposalService
from app.services.proposal_actions_service import undo_approval
from app.web.routes import main_routes


@pytest.fixture
def proposal_db(tmp_path, monkeypatch):
    path = tmp_path / "contracts.db"
    def connect():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    conn = connect()
    conn.executescript((Path(__file__).resolve().parents[1] / "app/db/schema.sql").read_text())
    run_migrations(conn.cursor())
    conn.execute("INSERT INTO members(id,username,password_hash) VALUES (1,'owner','unused')")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn.executemany("INSERT INTO proposals(id,title,amount,url,created_by,status,created_at) VALUES (?, ?, 10, 'https://shop.example/item',1,?,?)", [
        (1, "Recent", "active", now.isoformat()), (2, "Old", "active", (now - timedelta(days=40)).isoformat()),
        (3, "Approved", "approved", (now - timedelta(days=1)).isoformat())])
    conn.execute("INSERT INTO votes(proposal_id,member_id,vote) VALUES (1,1,'in_favor')")
    conn.execute("INSERT INTO comments(proposal_id,member_id,content) VALUES (1,1,'comment')")
    conn.executemany("INSERT INTO settings(key,value) VALUES (?,?)", [('url','https://vote.example'), ('threshold_default','10'), ('threshold_basic','5'), ('threshold_over50','20'), ('current_budget','100')])
    conn.execute("INSERT INTO activity_log(amount,description) VALUES (100,'Seed')")
    conn.commit()
    monkeypatch.setattr(main_routes, 'get_db', connect)
    monkeypatch.setattr(main_routes, 'ADMIN_API_KEY', 'contract-key')
    monkeypatch.setattr(mcp_server, 'DB_PATH', str(path))
    monkeypatch.setattr(mcp_server, 'MCP_API_KEY', 'mcp-contract-key')
    monkeypatch.setitem(app.config, 'TESTING', True)
    yield conn, connect
    conn.close()


def mcp_list(arguments):
    response = mcp_server.execute_tool_command('list_proposals', arguments, req_id=42)
    if 'error' in response:
        return response
    return json.loads(response['result']['content'][0]['text'])


def test_read_shapes_types_filters_pagination_and_resources(proposal_db):
    client = app.test_client()
    rest = client.get('/api/proposals?limit=1', headers={'X-Admin-Key':'contract-key'}).get_json()
    mcp = mcp_list({'limit':1})
    for result in (rest, mcp):
        assert (result['count'], result['limit'], result['offset']) == (1,1,0)
        row = result['proposals'][0]
        assert row['id'] == 1 and row['title'] == 'Recent'
        for key in ('id','created_by','basic_supplies','yes_votes','no_votes'):
            assert type(row[key]) is int
        assert type(row['amount']) is float
        assert (row['yes_votes'],row['no_votes']) == (1,0)
        assert row['url'] == 'https://shop.example/item'
        assert isinstance(row['created_at'],str) and row['status'] == 'active'
        assert isinstance(row['description'], (str,type(None)))
    assert rest['success'] is True and 'success' not in mcp
    assert set(rest['proposals'][0]) == {'id','title','description','amount','url','created_by','status','created_at','basic_supplies','yes_votes','no_votes'}
    richer = mcp['proposals'][0]
    assert richer['proposal_url'] == 'https://vote.example/proposal/1'
    assert richer['image_url'] is None and richer['purchased_at'] is None
    assert richer['processed_at'] is None and richer['over_budget_at'] is None
    assert richer['username'] == 'owner'
    assert richer['comments'][0]['content'] == 'comment'
    assert richer['votes'][0]['vote'] == 'in_favor'
    for age, expected in [('old',2),('recent',1)]:
        rest = client.get(f'/api/proposals?age={age}', headers={'X-Admin-Key':'contract-key'}).get_json()
        assert [r['id'] for r in rest['proposals']] == [expected]
        assert [r['id'] for r in mcp_list({'age':age})['proposals']] == [expected]
    assert mcp_list({'proposal_id':999})['proposals'] == []
    assert mcp_list({'limit':1,'offset':1})['proposals'][0]['id'] == 3


@pytest.mark.parametrize('arguments', [{'status':'bogus'},{'age':'bogus'},{'status':'approved','age':'old'},{'limit':0},{'limit':201},{'offset':-1}])
def test_contract_rejections_retain_transport_envelopes(proposal_db, arguments):
    response = app.test_client().get('/api/proposals', query_string=arguments, headers={'X-Admin-Key':'contract-key'})
    assert response.status_code == 400
    error = response.get_json()['error']
    assert isinstance(error['code'],str) and isinstance(error['message'],str)
    error = mcp_list(arguments)
    assert error['jsonrpc'] == '2.0' and error['id'] == 42
    assert error['error']['code'] == -32602
    assert app.test_client().get('/api/proposals').status_code == 401


def service(conn):
    return ProposalService(conn, Mock(), lambda:'https://vote.example', created_by=1)


def test_retry_and_concurrent_approval_apply_one_debit(proposal_db):
    conn, connect = proposal_db
    gate = threading.Barrier(2)
    def approve():
        with connect() as worker:
            gate.wait(timeout=5)
            return service(worker).process_proposal(1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(), range(2)))
    assert results.count(True) == 1
    assert service(conn).process_proposal(1) is None
    assert conn.execute('SELECT SUM(amount) FROM activity_log').fetchone()[0] == 90
    assert conn.execute('SELECT COUNT(*) FROM activity_log WHERE proposal_id=1').fetchone()[0] == 1
    assert conn.execute("SELECT value FROM settings WHERE key='current_budget'").fetchone()[0] == '90.0'


def test_failed_approval_rolls_back_state_balance_and_ledger(proposal_db):
    conn, _ = proposal_db
    conn.execute("CREATE TRIGGER stop_ledger BEFORE INSERT ON activity_log BEGIN SELECT RAISE(ABORT,'ledger failure'); END")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        service(conn).process_proposal(1)
    assert not conn.in_transaction
    assert conn.execute('SELECT status FROM proposals WHERE id=1').fetchone()[0] == 'active'
    assert conn.execute("SELECT value FROM settings WHERE key='current_budget'").fetchone()[0] == '100'
    assert conn.execute('SELECT SUM(amount) FROM activity_log').fetchone()[0] == 100
    conn.execute('DROP TRIGGER stop_ledger')
    conn.commit()
    assert service(conn).process_proposal(1) is True


def test_over_budget_rechecks_and_undo_reapproval_are_idempotent(proposal_db):
    conn, _ = proposal_db
    conn.execute('UPDATE proposals SET amount=150 WHERE id=1')
    conn.commit()
    worker = service(conn)
    assert worker.process_proposal(1) == 'over_budget'
    conn.execute("INSERT INTO activity_log(amount,description) VALUES (100,'Topup')")
    conn.commit()
    worker.check_over_budget_proposals()
    worker.check_over_budget_proposals()
    assert conn.execute('SELECT SUM(amount) FROM activity_log').fetchone()[0] == 50
    assert undo_approval(conn, proposal_id=1, member_id=1, is_admin=True,
                         process_proposal=worker.process_proposal, check_over_budget_proposals=worker.check_over_budget_proposals)
    assert conn.execute('SELECT SUM(amount) FROM activity_log').fetchone()[0] == 50
    assert conn.execute('SELECT status FROM proposals WHERE id=1').fetchone()[0] == 'approved'
    assert conn.execute('SELECT COUNT(*) FROM activity_log WHERE proposal_id=1').fetchone()[0] == 3
    assert worker.process_proposal(1) is None


def test_concurrent_undo_without_reapproval_restores_once(proposal_db):
    conn, connect = proposal_db
    service(conn).process_proposal(1)
    gate = threading.Barrier(2)
    def undo():
        with connect() as worker:
            gate.wait(timeout=5)
            return undo_approval(worker, proposal_id=1, member_id=1, is_admin=True,
                                 process_proposal=lambda _:None, check_over_budget_proposals=lambda:None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:undo(),range(2)))
    assert results.count(True) == 1
    assert conn.execute('SELECT SUM(amount) FROM activity_log').fetchone()[0] == 100


@pytest.mark.parametrize('mode,web_enabled', [('both',True),('web_only',True),('telegram_only',False)])
def test_cross_channel_vote_controls_and_guidance_matrix(proposal_db, mode, web_enabled):
    from app.integrations.telegram_webhook import proposal_vote_response_text, poll_vote_response_text
    conn, _ = proposal_db
    conn.execute("INSERT INTO polls(question,options_json,created_by) VALUES ('Choose?', '[\"A\",\"B\"]',1)")
    conn.executemany("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", [('proposal_vote_mode',mode),('poll_vote_mode',mode)])
    conn.commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(member_id=1,username='owner',is_admin=False,lang='en')
    for path, marker in [('/proposals','value="in_favor"'),('/proposal/1','value="in_favor"'),('/polls','name="option_index"')]:
        response = client.get(path)
        assert response.status_code == 200
        assert (marker in response.get_data(as_text=True)) is web_enabled
    if mode == 'web_only':
        assert 'disabled' in proposal_vote_response_text(False,'telegram_disabled')
        assert 'disabled' in poll_vote_response_text(False,'telegram_disabled')
    else:
        assert 'recorded' in proposal_vote_response_text(True,None)
        assert 'recorded' in poll_vote_response_text(True,None)
