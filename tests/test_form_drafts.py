"""Only successful web submissions acknowledge drafts; no draft text enters cookies."""
from unittest.mock import Mock
import pytest

from test_admin_interface import ui_client
from app import app
from app.web.routes import main_routes


@pytest.fixture
def draft_client(ui_client,monkeypatch):
    monkeypatch.setitem(app.config,'WTF_CSRF_ENABLED',False)
    monkeypatch.setattr(main_routes,'process_proposal',Mock())
    monkeypatch.setattr(main_routes,'send_telegram_message',Mock(return_value=True))
    monkeypatch.setattr(main_routes,'TelegramClient',Mock())
    conn=main_routes.get_db()
    conn.execute("INSERT INTO comments(id,proposal_id,member_id,content) VALUES (1,1,1,'Original comment')")
    conn.commit();conn.close()
    return ui_client


@pytest.mark.parametrize('path,data,key',[
    ('/proposal/new',{'title':'Draft proposal','description':'Keep this text','amount':'10'},'proposal:new'),
    ('/proposal/1/edit',{'title':'Changed title','description':'Keep this text','amount':'10'},'proposal:edit:1'),
    ('/proposal/1',{'comment':'Keep this text'},'proposal:comment:1'),
    ('/comment/1/edit',{'content':'Keep this text'},'comment:edit:1'),
    ('/group-purchases/new',{'title':'Draft order','component_name':'AA','component_price':'2'},'group:new'),
    ('/settings',{'action':'submit_feedback','category':'suggestion','message':'Keep this text','section':'/about','return_to':'/about'},'feedback:/about'),
])
def test_success_acknowledges_only_the_submitted_nonce(draft_client,path,data,key):
    response=draft_client.post(path,data={**data,'_draft_nonce':'draft-test-123'})
    assert response.status_code==302
    with draft_client.session_transaction() as session:
        assert session['_draft_receipts']==[{'key':key,'nonce':'draft-test-123'}]
        assert 'Keep this text' not in str(dict(session))
    page=draft_client.get('/about').get_data(as_text=True)
    assert 'name="draft-owner" content="1"' in page
    assert 'draft-test-123' in page
    with draft_client.session_transaction() as session:assert '_draft_receipts' not in session


def test_poll_success_is_acknowledged_in_the_rendered_response(draft_client):
    response=draft_client.post('/admin',data={'action':'create_poll','question':'Which workshop next?','options':'A\nB','closes_at':'2099-01-01T12:00','_draft_nonce':'poll-test-123'})
    assert response.status_code==200
    assert b'poll-test-123' in response.data
    assert b'poll:new' in response.data


def test_validation_failure_never_clears_a_draft(draft_client):
    response=draft_client.post('/proposal/new',data={'title':'Keep title','description':'Keep text','amount':'-10','_draft_nonce':'failed-nonce'})
    assert response.status_code==200
    with draft_client.session_transaction() as session:assert not session.get('_draft_receipts')
    assert b'failed-nonce' not in response.data


def test_group_edit_acknowledges_its_record_specific_draft(draft_client):
    created=draft_client.post('/group-purchases/new',data={'title':'Shared order','component_name':'AA','component_price':'2'})
    assert created.status_code==302
    edited=draft_client.post('/group-purchases/1/edit',data={'title':'Edited shared order','description':'Keep private text','component_name_1':'AA','component_price_1':'3','_draft_nonce':'group-edit-123'})
    assert edited.status_code==302
    with draft_client.session_transaction() as session:
        assert session['_draft_receipts']==[{'key':'group:edit:1','nonce':'group-edit-123'}]
        assert 'Keep private text' not in str(dict(session))


def test_drafts_are_opt_in_and_accounts_identify_their_own_storage(draft_client):
    html=draft_client.get('/proposal/new').get_data(as_text=True)
    assert 'data-draft-key="proposal:new"' in html
    assert 'data-draft-fields="title description amount url voting_deadline basic_supplies"' in html
    with draft_client.session_transaction() as session:session['member_id']=2
    assert b'name="draft-owner" content="2"' in draft_client.get('/about').data
