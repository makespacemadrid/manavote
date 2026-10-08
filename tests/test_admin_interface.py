"""Password-dialog markup/form contracts and administrator-only link diagnostics."""
import os
import sqlite3
from pathlib import Path

import pytest

from app import app
from app.db.migrations import run_migrations
from app.web.routes import main_routes


@pytest.fixture
def ui_client(tmp_path, monkeypatch):
    path = tmp_path / 'ui.db'
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    conn = connect()
    conn.executescript((Path(__file__).resolve().parents[1] / 'app/db/schema.sql').read_text())
    run_migrations(conn.cursor())
    conn.executemany("INSERT INTO members(id,username,password_hash,is_admin,last_linked_at,last_unlinked_at) VALUES (?,?,'unused',?,?,?)", [
        (1,'admin',1,None,None), (2,'O\'Brien <member>',0,'2026-10-08T10:00:00Z','2026-10-07T10:00:00Z')])
    conn.execute("INSERT INTO settings(key,value) VALUES ('timezone','Europe/Madrid')")
    conn.execute("INSERT INTO proposals(id,title,amount,created_by) VALUES (1,'Proposal',10,1)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(main_routes,'get_db',connect)
    monkeypatch.setattr(main_routes,'DB_PATH',str(path))
    monkeypatch.setitem(app.config,'TESTING',True)
    client=app.test_client()
    with client.session_transaction() as session:
        session.update(member_id=1,username='admin',is_admin=True,lang='en')
    return client


@pytest.mark.parametrize('language,history,images', [('en','Full Proposal History','Backup Uploaded Images'),('es','Historial completo de propuestas','Copia de seguridad de imágenes subidas')])
def test_password_dialog_and_translated_diagnostics(ui_client, language, history, images):
    with ui_client.session_transaction() as session:
        session['lang']=language
    response=ui_client.get('/admin')
    assert response.status_code == 200
    html=response.get_data(as_text=True)
    assert f'<h3>{history}</h3>' in html
    assert images in html
    assert html.count('id="changePasswordTitle"') == 1
    assert 'aria-labelledby="changePasswordTitle"' in html and 'aria-modal="true"' in html
    assert 'for="newPassword"' in html and 'for="confirmPassword"' in html
    assert 'data-password-open data-member-id="2"' in html
    assert 'data-username="O&#39;Brien &lt;member&gt;"' in html
    for field in ('csrf_token','action','member_id','new_password','confirm_password'):
        assert f'name="{field}"' in html
    assert 'value="change_user_password"' in html
    assert '2026-10-08 12:00' in html and '2026-10-07 12:00' in html
    assert ('Not recorded' if language == 'en' else 'Sin registro') in html
    assert 'showChangePassword' not in html
    capture=os.getenv('MANAVOTE_UI_CAPTURE_DIR')
    if capture:
        output=Path(capture); output.mkdir(parents=True,exist_ok=True)
        base=Path(__file__).resolve().parents[1]
        html=html.replace('/static/', (base/'static').as_uri()+'/')
        (output/f'admin-{language}.html').write_text(html)
        (output/f'proposals-{language}.html').write_text(ui_client.get('/proposals').get_data(as_text=True).replace('/static/',(base/'static').as_uri()+'/'))


def test_regular_member_cannot_read_admin_diagnostics(ui_client):
    with ui_client.session_transaction() as session:
        session.update(member_id=2,username='member',is_admin=False)
    response=ui_client.get('/admin')
    assert response.status_code in (302,403)
    assert b'last_linked_at' not in response.data


def test_assistant_health_is_admin_only_and_contains_safe_aggregate_fields(ui_client, monkeypatch):
    from app.integrations.assistant_jobs import AssistantJobs
    jobs=AssistantJobs()
    jobs.reject('member_capacity_exceeded')
    monkeypatch.setattr(main_routes,'_telegram_jobs',jobs)
    monkeypatch.setenv('OCABRA_API_KEY','private-health-credential')
    monkeypatch.setenv('OCABRA_CHAT_URL','https://user:private-health-password@example.test/chat')
    response=ui_client.get('/admin/assistant-health')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    payload=response.get_json()
    assert payload['scope'] == 'process' and payload['reset'] == 'process_restart'
    assert payload['terminal']['rejected'] == 1
    assert payload['reasons']['member_capacity_exceeded'] == 1
    assert {'queue','model','mcp','delivery'} == set(payload['latency_ms'])
    for private in ('private-health-credential','private-health-password','example.test','telegram_user_id','chat_id','actor_member_id'):
        assert private not in response.get_data(as_text=True)
    with ui_client.session_transaction() as session:
        session.update(member_id=2,is_admin=False)
    assert ui_client.get('/admin/assistant-health').status_code == 302
    assert app.test_client().get('/admin/assistant-health').status_code == 302
