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


@pytest.fixture
def error_store(ui_client, tmp_path, monkeypatch):
    import logging
    from app.repositories.error_report_repo import ErrorReportRepository
    from app.integrations.error_reporting import ErrorReportHandler
    repo = ErrorReportRepository(tmp_path / 'diagnostics.db')
    monkeypatch.setitem(app.extensions, 'error_reports', repo)
    handler = ErrorReportHandler(repo)
    logging.getLogger().addHandler(handler)
    yield repo
    logging.getLogger().removeHandler(handler)
    handler.close()


def test_errors_tab_precedes_feedback_and_download_contains_verbose_trace(ui_client, error_store, monkeypatch):
    import logging
    monkeypatch.setenv('ADMIN_API_KEY', 'do-not-export-this-secret')
    logger = logging.getLogger('manavote.test.errors')
    try:
        raise ValueError('request failed api_key=do-not-export-this-secret <script>bad</script>')
    except ValueError:
        logger.exception('Failed operation')
    response = ui_client.get('/admin?tab=errors')
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    assert html.index('data-section="errors"') < html.index('data-section="feedback"')
    assert 'Traceback' in html and 'ValueError' in html
    assert '<script>bad</script>' not in html
    assert 'do-not-export-this-secret' not in html
    report = ui_client.get('/admin/errors/download')
    assert report.status_code == 200
    assert report.headers['Cache-Control'] == 'no-store'
    assert 'attachment;' in report.headers['Content-Disposition']
    assert report.mimetype == 'application/json'
    data = report.get_json()
    assert data['errors'][0]['logger'] == 'manavote.test.errors'
    assert 'test_admin_interface.py' in data['errors'][0]['details']
    assert 'do-not-export-this-secret' not in report.get_data(as_text=True)
    assert '[REDACTED]' in report.get_data(as_text=True)


@pytest.mark.parametrize('role', ['anonymous', 'member', 'api_key'])
def test_error_download_is_session_admin_only(ui_client, error_store, role, monkeypatch):
    with ui_client.session_transaction() as session:
        session.clear()
        if role == 'member':
            session.update(member_id=2, username='member', is_admin=False)
    monkeypatch.setattr(main_routes, 'ADMIN_API_KEY', 'admin-api-key')
    response = ui_client.get('/admin/errors/download', headers={'X-Admin-Key': 'admin-api-key'})
    assert response.status_code in (302, 403)
    assert b'"errors"' not in response.data


def test_empty_and_spanish_errors_view(ui_client, error_store):
    with ui_client.session_transaction() as session:
        session['lang'] = 'es'
    html = ui_client.get('/admin?tab=errors').get_data(as_text=True)
    assert 'Errores' in html and 'Descargar informe de errores' in html
    assert 'Todavía no se han registrado errores.' in html
    assert ui_client.get('/admin/errors/download').get_json()['errors'] == []


def test_error_capture_is_bounded_persistent_and_scrubs_again_on_export(error_store, monkeypatch):
    import logging
    from app.integrations.error_reporting import ErrorReportHandler
    from app.repositories.error_report_repo import ErrorReportRepository
    from app.services.error_report_service import list_errors
    handler = ErrorReportHandler(error_store)
    for i in range(205):
        handler.handle(logging.LogRecord('test', logging.ERROR, __file__, 1, f'{i}: ' + 'x' * 18000, (), None))
    persisted = ErrorReportRepository(error_store.path)
    rows = persisted.recent()
    assert len(rows) == 200
    assert all(len(row['details']) <= 16000 for row in rows)
    assert '204:' in rows[0]['details'] and '5:' in rows[-1]['details']
    error_store.append('2026-10-29T10:00:00+00:00', 'ERROR', 'test', 'a-secret-configured-later')
    monkeypatch.setenv('MCP_API_KEY', 'a-secret-configured-later')
    assert list_errors(persisted)[0]['details'] == '[REDACTED]'


def test_diagnostic_failure_does_not_break_logging_and_admin_shows_unavailable(error_store, ui_client, monkeypatch):
    import logging
    import sqlite3
    from app.integrations.error_reporting import ErrorReportHandler
    def unavailable(*args):
        raise sqlite3.OperationalError('private error')
    monkeypatch.setattr(error_store, 'append', unavailable)
    monkeypatch.setattr(error_store, 'recent', unavailable)
    ErrorReportHandler(error_store).handle(logging.LogRecord('test', logging.ERROR, __file__, 1, 'failure', (), None))
    response = ui_client.get('/admin/errors/download')
    assert response.status_code == 200
    assert 'storage is unavailable' in response.get_json()['errors'][0]['details']
    assert b'private error' not in response.data


def test_uncaught_request_error_is_captured_with_traceback(ui_client, error_store, monkeypatch):
    from app.services import admin_page_service
    monkeypatch.setitem(app.config, 'PROPAGATE_EXCEPTIONS', False)
    def fail_page(*args, **kwargs):
        raise RuntimeError('admin page failure fixture')
    monkeypatch.setattr(admin_page_service, 'build_admin_page', fail_page)
    assert ui_client.get('/admin').status_code == 500
    report = ui_client.get('/admin/errors/download').get_json()
    assert any('RuntimeError: admin page failure fixture' in row['details'] and 'fail_page' in row['details'] for row in report['errors'])
