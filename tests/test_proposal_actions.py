"""Use-case and Flask contracts for the extracted purchase/deletion paths."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app import app
from app.db.migrations import run_migrations
from app.services import proposal_actions_service as actions
from app.web.routes import main_routes


@pytest.fixture
def action_db(tmp_path, monkeypatch):
    path = tmp_path / "proposal_actions.db"

    def connect():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    connection = connect()
    connection.executescript((Path(__file__).resolve().parents[1] / "app/db/schema.sql").read_text())
    run_migrations(connection.cursor())
    connection.executemany(
        "INSERT INTO members (id, username, password_hash) VALUES (?, ?, 'unused')",
        [(1, "owner"), (2, "other")],
    )
    connection.executemany(
        "INSERT INTO proposals (id, title, amount, created_by, status, processed_at) VALUES (?, 'proposal', 10, 1, ?, ?)",
        [(1, "active", None), (2, "approved", "2026-10-01"), (3, "over_budget", "2026-10-01"), (4, "rejected", "2026-10-01")],
    )
    connection.executemany(
        "INSERT INTO comments (id, proposal_id, member_id, content) VALUES (?, ?, 1, 'comment')",
        [(1, 1), (2, 2)],
    )
    connection.executemany(
        "INSERT INTO votes (proposal_id, member_id, vote) VALUES (?, 1, 'in_favor')",
        [(1,), (2,)],
    )
    connection.execute("INSERT INTO activity_log (amount, description) VALUES (100, 'budget')")
    connection.execute("INSERT INTO settings (key, value) VALUES ('current_budget', '100')")
    connection.commit()
    monkeypatch.setattr(main_routes, "get_db", connect)
    monkeypatch.setitem(app.config, "TESTING", True)
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    yield connection, connect
    connection.close()


def _client(member_id=2, *, is_admin=False):
    client = app.test_client()
    if member_id is not None:
        with client.session_transaction() as user_session:
            user_session.update(member_id=member_id, username="member", is_admin=is_admin)
    return client


def test_purchase_and_unpurchase_commit_timestamp_only_for_approved_proposal(action_db, caplog):
    connection, connect = action_db
    stamp = datetime(2026, 10, 8, 13, 30)
    with caplog.at_level("INFO", logger=actions.__name__):
        actions.set_purchase_state(connection, proposal_id=2, member_id=2, purchased=True, now=stamp)
    with connect() as reader:
        row = reader.execute("SELECT status, processed_at, purchased_at FROM proposals WHERE id = 2").fetchone()
        assert tuple(row) == ("approved", "2026-10-01", stamp.isoformat())
        assert reader.execute("SELECT SUM(amount) FROM activity_log").fetchone()[0] == 100
    assert "event=proposal_purchase_updated actor_id=2 proposal_id=2 purchased=True reason_code=ok" in caplog.text
    actions.set_purchase_state(connection, proposal_id=2, member_id=2, purchased=False)
    assert connection.execute("SELECT purchased_at FROM proposals WHERE id = 2").fetchone()[0] is None


@pytest.mark.parametrize("proposal_id,code", [(1, "proposal_not_approved"), (3, "proposal_not_approved"), (4, "proposal_not_approved"), (999, "proposal_not_found")])
@pytest.mark.parametrize("purchased", [True, False])
def test_purchase_rejections_do_not_mutate_rows(action_db, proposal_id, code, purchased):
    connection, _ = action_db
    before = [tuple(row) for row in connection.execute("SELECT * FROM proposals ORDER BY id")]
    with pytest.raises(actions.ProposalActionError) as caught:
        actions.set_purchase_state(connection, proposal_id=proposal_id, member_id=2, purchased=purchased)
    assert caught.value.code == code
    assert [tuple(row) for row in connection.execute("SELECT * FROM proposals ORDER BY id")] == before


@pytest.mark.parametrize("member_id,is_admin", [(1, False), (2, True)])
def test_owner_or_admin_deletes_only_selected_active_proposal_and_dependents(action_db, member_id, is_admin):
    connection, connect = action_db
    actions.delete_proposal(connection, proposal_id=1, member_id=member_id, is_admin=is_admin)
    with connect() as reader:
        assert reader.execute("SELECT 1 FROM proposals WHERE id = 1").fetchone() is None
        assert reader.execute("SELECT 1 FROM votes WHERE proposal_id = 1").fetchone() is None
        assert reader.execute("SELECT 1 FROM comments WHERE proposal_id = 1").fetchone() is None
        assert reader.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 3
        assert reader.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 1
        assert reader.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1
        assert reader.execute("SELECT SUM(amount) FROM activity_log").fetchone()[0] == 100


@pytest.mark.parametrize("proposal_id,is_admin,code", [
    (1, False, "proposal_owner_required"), (2, True, "proposal_processed"),
    (3, True, "proposal_processed"), (4, True, "proposal_processed"),
    (999, True, "proposal_not_found"),
])
def test_proposal_deletion_enforces_existing_owner_and_status_rules(action_db, proposal_id, is_admin, code):
    connection, _ = action_db
    with pytest.raises(actions.ProposalActionError) as caught:
        actions.delete_proposal(connection, proposal_id=proposal_id, member_id=2, is_admin=is_admin)
    assert caught.value.code == code
    assert connection.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 4
    assert connection.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 2


def test_failed_proposal_delete_rolls_back_prior_vote_and_comment_deletes(action_db, caplog):
    connection, _ = action_db
    connection.execute("CREATE TRIGGER stop_delete BEFORE DELETE ON proposals BEGIN SELECT RAISE(ABORT, 'delete blocked'); END")
    connection.commit()
    with caplog.at_level("INFO", logger=actions.__name__), pytest.raises(sqlite3.IntegrityError, match="delete blocked"):
        actions.delete_proposal(connection, proposal_id=1, member_id=1, is_admin=False)
    assert connection.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 4
    assert connection.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 2
    assert "event=proposal_deleted" not in caplog.text


def test_comment_delete_is_admin_only_and_returns_parent_without_affecting_proposal(action_db):
    connection, _ = action_db
    with pytest.raises(actions.ProposalActionError) as caught:
        actions.delete_comment(connection, comment_id=1, member_id=1, is_admin=False)
    assert caught.value.code == "admin_required"
    assert actions.delete_comment(connection, comment_id=1, member_id=2, is_admin=True) == 1
    assert connection.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 4
    assert connection.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1
    with pytest.raises(actions.ProposalActionError) as caught:
        actions.delete_comment(connection, comment_id=1, member_id=2, is_admin=True)
    assert caught.value.code == "comment_not_found"


def test_comment_edit_preserves_identity_and_skips_empty_content(action_db, caplog):
    connection, _ = action_db
    before = dict(connection.execute("SELECT * FROM comments WHERE id = 1").fetchone())
    with caplog.at_level("INFO", logger=actions.__name__):
        assert actions.update_comment(connection, comment_id=1, member_id=2, is_admin=True, content="  revised  ") == {"proposal_id": 1, "updated": True}
    after = dict(connection.execute("SELECT * FROM comments WHERE id = 1").fetchone())
    assert after == {**before, "content": "revised"}
    assert "event=proposal_comment_updated actor_id=2 proposal_id=1 comment_id=1 reason_code=ok" in caplog.text
    assert "revised" not in caplog.text
    assert actions.update_comment(connection, comment_id=1, member_id=2, is_admin=True, content=" \n ") == {"proposal_id": 1, "updated": False}
    assert connection.execute("SELECT content FROM comments WHERE id = 1").fetchone()[0] == "revised"


@pytest.mark.parametrize("comment_id,is_admin,code", [(1, False, "admin_required"), (999, True, "comment_not_found")])
def test_comment_edit_rejects_non_admin_or_missing_comment(action_db, comment_id, is_admin, code):
    connection, _ = action_db
    with pytest.raises(actions.ProposalActionError) as caught:
        actions.update_comment(connection, comment_id=comment_id, member_id=2, is_admin=is_admin, content="replacement")
    assert caught.value.code == code
    assert connection.execute("SELECT content FROM comments WHERE id = 1").fetchone()[0] == "comment"


def test_comment_edit_routes_keep_admin_access_missing_lookup_and_empty_noop(action_db):
    connection, _ = action_db
    other = _client(2)
    assert other.get("/comment/1/edit").headers["Location"].endswith("/proposals")
    assert other.post("/comment/1/edit", data={"content": "wrong"}).headers["Location"].endswith("/proposals")
    admin = _client(2, is_admin=True)
    assert admin.get("/comment/1/edit").status_code == 200
    assert admin.post("/comment/999/edit").headers["Location"].endswith("/proposals")
    response = admin.post("/comment/1/edit", data={"content": "  edited  "})
    assert response.headers["Location"].endswith("/proposal/1")
    assert connection.execute("SELECT content FROM comments WHERE id = 1").fetchone()[0] == "edited"
    assert admin.post("/comment/1/edit", data={"content": "   "}).headers["Location"].endswith("/proposal/1")
    assert connection.execute("SELECT content FROM comments WHERE id = 1").fetchone()[0] == "edited"


@pytest.mark.parametrize("path", ["/purchase/2", "/unpurchase/2", "/proposal/1/delete", "/comment/1/delete"])
def test_action_routes_remain_post_only_and_require_login(action_db, path):
    assert _client().get(path).status_code == 405
    response = _client(None).post(path)
    assert response.status_code == 302 and response.headers["Location"].endswith("/login")


def test_purchase_routes_preserve_signed_in_member_access_redirects_and_flashes(action_db):
    connection, _ = action_db
    client = _client(2)
    for path, message in [("/purchase/2", "Marked as purchased!"), ("/unpurchase/2", "Purchase status removed")]:
        response = client.post(path)
        assert response.status_code == 302 and response.headers["Location"].endswith("/proposal/2")
        with client.session_transaction() as user_session:
            assert ("success", message) in user_session["_flashes"]
    assert connection.execute("SELECT purchased_at FROM proposals WHERE id = 2").fetchone()[0] is None
    assert client.post("/purchase/1").headers["Location"].endswith("/proposal/1")
    assert client.post("/unpurchase/1").headers["Location"].endswith("/proposals")
    assert client.post("/purchase/999").headers["Location"].endswith("/proposals")


def test_delete_routes_preserve_owner_admin_checks_and_parent_redirect(action_db):
    connection, _ = action_db
    other = _client(2)
    assert other.post("/proposal/1/delete").headers["Location"].endswith("/proposal/1")
    assert other.post("/comment/1/delete").headers["Location"].endswith("/proposals")
    assert connection.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 2
    admin = _client(2, is_admin=True)
    assert admin.post("/comment/1/delete").headers["Location"].endswith("/proposal/1")
    assert admin.post("/proposal/1/delete").headers["Location"].endswith("/proposals")
    assert admin.post("/comment/999/delete").headers["Location"].endswith("/proposals")


@pytest.mark.parametrize("path,function,is_admin", [
    ("/purchase/2", "set_purchase_state", False),
    ("/unpurchase/2", "set_purchase_state", False),
    ("/proposal/1/delete", "delete_proposal", False),
    ("/comment/1/delete", "delete_comment", True),
    ("/comment/1/edit", "get_comment_for_edit", True),
])
def test_action_routes_close_connection_after_unexpected_service_failure(action_db, monkeypatch, path, function, is_admin):
    from unittest.mock import Mock

    connection = Mock()
    monkeypatch.setattr(main_routes, "get_db", lambda: connection)
    def fail(*_args, **_kwargs):
        raise sqlite3.OperationalError("write failed")

    monkeypatch.setattr(actions, function, fail)
    with pytest.raises(sqlite3.OperationalError, match="write failed"):
        _client(1, is_admin=is_admin).post(path)
    connection.close.assert_called_once_with()


def test_withdraw_commits_only_actors_vote_before_reprocessing(action_db):
    connection, connect = action_db
    connection.execute("INSERT INTO votes (proposal_id, member_id, vote) VALUES (1, 2, 'against')")
    connection.commit()
    calls = []
    def process(proposal_id):
        with connect() as observer:
            assert observer.execute("SELECT member_id FROM votes WHERE proposal_id = 1").fetchall()[0][0] == 2
            assert observer.execute("SELECT COUNT(*) FROM votes WHERE proposal_id = 2").fetchone()[0] == 1
        calls.append(proposal_id)
    actions.withdraw_vote(connection, proposal_id=1, member_id=1, process_proposal=process)
    actions.withdraw_vote(connection, proposal_id=1, member_id=1, process_proposal=process)
    actions.withdraw_vote(connection, proposal_id=999, member_id=1, process_proposal=process)
    assert calls == [1, 1]


@pytest.mark.parametrize('proposal_id', [2, 3, 4])
def test_withdraw_rejects_processed_proposals_without_calling_processor(action_db, proposal_id):
    from unittest.mock import Mock
    connection, _ = action_db
    process = Mock()
    with pytest.raises(actions.ProposalActionError, match='proposal_processed'):
        actions.withdraw_vote(connection, proposal_id=proposal_id, member_id=1, process_proposal=process)
    process.assert_not_called()
    assert connection.execute('SELECT COUNT(*) FROM votes').fetchone()[0] == 2


def test_undo_restores_ledger_and_setting_before_ordered_callbacks(action_db):
    connection, connect = action_db
    connection.execute("UPDATE proposals SET purchased_at = '2026-10-02', over_budget_at = '2026-09-30' WHERE id = 2")
    connection.execute("UPDATE settings SET value = '-999' WHERE key = 'current_budget'")
    connection.commit()
    callbacks = []
    def process(proposal_id):
        with connect() as observer:
            row = observer.execute('SELECT * FROM proposals WHERE id = ?', (proposal_id,)).fetchone()
            assert row['status'] == 'active'
            assert row['processed_at'] is None and row['purchased_at'] is None
            assert row['over_budget_at'] == '2026-09-30'
            assert float(observer.execute("SELECT value FROM settings WHERE key = 'current_budget'").fetchone()[0]) == 110
            log = observer.execute('SELECT * FROM activity_log ORDER BY id DESC').fetchone()
            assert log['amount'] == 10 and log['proposal_id'] == 2
            assert log['description'] == 'Undo approval: proposal' and log['created_by'] is None
        callbacks.append(('process', proposal_id))
    assert actions.undo_approval(connection, proposal_id=2, member_id=2, is_admin=True,
        process_proposal=process, check_over_budget_proposals=lambda: callbacks.append(('pending', None)))
    assert callbacks == [('process', 2), ('pending', None)]
    assert not actions.undo_approval(connection, proposal_id=2, member_id=2, is_admin=True,
        process_proposal=process, check_over_budget_proposals=lambda: callbacks.append('wrong'))
    assert len(callbacks) == 2


@pytest.mark.parametrize('proposal_id', [1, 3, 4, 999])
def test_undo_unapproved_is_silent_noop(action_db, proposal_id):
    from unittest.mock import Mock
    connection, _ = action_db
    callback = Mock()
    assert not actions.undo_approval(connection, proposal_id=proposal_id, member_id=2, is_admin=True,
        process_proposal=callback, check_over_budget_proposals=callback)
    callback.assert_not_called()
    assert connection.execute('SELECT SUM(amount) FROM activity_log').fetchone()[0] == 100


def test_undo_requires_admin_and_rolls_back_all_writes_on_ledger_failure(action_db):
    from unittest.mock import Mock
    connection, _ = action_db
    callback = Mock()
    kwargs = dict(proposal_id=2, member_id=1, process_proposal=callback, check_over_budget_proposals=callback)
    with pytest.raises(actions.ProposalActionError, match='admin_required'):
        actions.undo_approval(connection, is_admin=False, **kwargs)
    before = dict(connection.execute('SELECT * FROM proposals WHERE id = 2').fetchone())
    setting = connection.execute("SELECT value FROM settings WHERE key = 'current_budget'").fetchone()[0]
    connection.execute("CREATE TRIGGER stop_undo BEFORE INSERT ON activity_log BEGIN SELECT RAISE(ABORT, 'ledger blocked'); END")
    connection.commit()
    with pytest.raises(sqlite3.IntegrityError, match='ledger blocked'):
        actions.undo_approval(connection, is_admin=True, **kwargs)
    assert dict(connection.execute('SELECT * FROM proposals WHERE id = 2').fetchone()) == before
    assert connection.execute("SELECT value FROM settings WHERE key = 'current_budget'").fetchone()[0] == setting
    callback.assert_not_called()


@pytest.mark.parametrize('path,function,is_admin', [('/withdraw-vote/1', 'withdraw_vote', False), ('/undo/2', 'undo_approval', True)])
def test_lifecycle_routes_close_connection_after_unexpected_failure(action_db, monkeypatch, path, function, is_admin):
    test_action_routes_close_connection_after_unexpected_service_failure(action_db, monkeypatch, path, function, is_admin)


def test_lifecycle_routes_preserve_auth_flashes_and_callback_order(action_db, monkeypatch):
    calls = []
    monkeypatch.setattr(main_routes, 'process_proposal', lambda proposal_id: calls.append(proposal_id))
    monkeypatch.setattr(main_routes, 'check_over_budget_proposals', lambda: calls.append('pending'))
    client = _client(1)
    assert client.get('/withdraw-vote/1').status_code == 405
    assert _client(None).post('/withdraw-vote/1').headers['Location'].endswith('/login')
    assert client.post('/undo/2').headers['Location'].endswith('/proposals')
    assert not calls
    for proposal_id in [1, 2, 999]:
        assert client.post(f'/withdraw-vote/{proposal_id}').headers['Location'].endswith('/proposals')
    assert calls == [1]
    with client.session_transaction() as user_session:
        assert ('error', 'Cannot withdraw vote on processed proposals') in user_session['_flashes']
        assert ('success', 'Vote withdrawn!') in user_session['_flashes']
    admin = _client(2, is_admin=True)
    assert admin.post('/undo/2').headers['Location'].endswith('/proposals')
    assert calls == [1, 2, 'pending']
    with admin.session_transaction() as user_session:
        assert ('success', 'Approval undone, budget restored') in user_session['_flashes']
