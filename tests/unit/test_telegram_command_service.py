import sqlite3

from app.services import telegram_command_service


def _make_db(tmp_path):
    db_path = str(tmp_path / "telegram_commands.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE members (id INTEGER PRIMARY KEY, username TEXT, telegram_username TEXT, telegram_user_id INTEGER)"
    )
    conn.execute(
        "CREATE TABLE polls (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, options_json TEXT, status TEXT, closes_at TEXT)"
    )
    conn.execute("CREATE TABLE poll_votes (poll_id INTEGER, member_id INTEGER, option_index INTEGER, UNIQUE(poll_id, member_id))")
    conn.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, status TEXT)")
    conn.commit()
    conn.close()
    return db_path


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _settings(values=None):
    values = values or {}
    return lambda key, default=None: values.get(key, default)


def test_vote_command_rejected_when_telegram_disabled(tmp_path):
    db_path = _make_db(tmp_path)
    ok, reason = telegram_command_service.process_telegram_vote_command(
        lambda: _connect(db_path),
        _settings({"poll_vote_mode": "web_only"}),
        lambda message: None,
        "alice",
        "/vote 1",
    )
    assert (ok, reason) == (False, "telegram_disabled")


def test_vote_command_rejects_malformed_text(tmp_path):
    db_path = _make_db(tmp_path)
    ok, reason = telegram_command_service.process_telegram_vote_command(
        lambda: _connect(db_path), _settings(), lambda message: None, "alice", "/vote"
    )
    assert (ok, reason) == (False, "invalid_format")


def test_vote_command_rejects_unknown_member_without_telegram_user_id(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO polls (question, options_json, status) VALUES ('Snacks?', '[\"Yes\",\"No\"]', 'open')")
    conn.commit()
    conn.close()

    ok, reason = telegram_command_service.process_telegram_vote_command(
        lambda: _connect(db_path), _settings(), lambda message: None, "stranger", "/vote 1", telegram_user_id=None
    )
    assert (ok, reason) == (False, "unknown_member")


def test_vote_command_allows_unlinked_telegram_user_when_not_required(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO polls (question, options_json, status) VALUES ('Snacks?', '[\"Yes\",\"No\"]', 'open')")
    conn.commit()
    conn.close()

    ok, reason = telegram_command_service.process_telegram_vote_command(
        lambda: _connect(db_path), _settings(), lambda message: None, "stranger", "/vote 1", telegram_user_id=999
    )
    assert (ok, reason) == (True, "ok")


def test_vote_command_requires_link_when_setting_enabled(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO polls (question, options_json, status) VALUES ('Snacks?', '[\"Yes\",\"No\"]', 'open')")
    conn.commit()
    conn.close()

    ok, reason = telegram_command_service.process_telegram_vote_command(
        lambda: _connect(db_path),
        _settings({"telegram_require_linked_vote": "true"}),
        lambda message: None,
        "stranger",
        "/vote 1",
        telegram_user_id=999,
    )
    assert (ok, reason) == (False, "link_required")


def test_vote_command_records_vote_for_linked_member(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO members (username, telegram_user_id) VALUES ('alice', 42)")
    conn.execute("INSERT INTO polls (question, options_json, status) VALUES ('Snacks?', '[\"Yes\",\"No\"]', 'open')")
    conn.commit()
    conn.close()

    ok, reason = telegram_command_service.process_telegram_vote_command(
        lambda: _connect(db_path), _settings(), lambda message: None, "alice", "/vote 2", telegram_user_id=42
    )

    assert (ok, reason) == (True, "ok")
    conn = _connect(db_path)
    row = conn.execute("SELECT option_index FROM poll_votes").fetchone()
    conn.close()
    assert row["option_index"] == 1


def test_proposal_vote_command_rejected_when_record_returns_false(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO members (id, username, telegram_user_id) VALUES (1, 'alice', 42)")
    conn.execute("INSERT INTO proposals (id, status) VALUES (7, 'active')")
    conn.commit()
    conn.close()

    ok, reason = telegram_command_service.process_telegram_proposal_vote_command(
        lambda: _connect(db_path), _settings(), lambda *a, **kw: False, "alice", "/pvote 7 yes", telegram_user_id=42
    )
    assert (ok, reason) == (False, "telegram_disabled")


def test_proposal_vote_command_succeeds_and_forwards_source_telegram(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO members (id, username, telegram_user_id) VALUES (1, 'alice', 42)")
    conn.execute("INSERT INTO proposals (id, status) VALUES (7, 'active')")
    conn.commit()
    conn.close()
    recorded = []

    def record_proposal_vote(proposal_id, member_id, vote, source):
        recorded.append((proposal_id, member_id, vote, source))
        return True

    ok, reason = telegram_command_service.process_telegram_proposal_vote_command(
        lambda: _connect(db_path), _settings(), record_proposal_vote, "alice", "/pvote 7 yes", telegram_user_id=42
    )

    assert (ok, reason) == (True, "ok")
    assert recorded == [(7, 1, "in_favor", "telegram")]


def test_proposal_vote_command_rejects_closed_proposal(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO members (id, username, telegram_user_id) VALUES (1, 'alice', 42)")
    conn.execute("INSERT INTO proposals (id, status) VALUES (7, 'approved')")
    conn.commit()
    conn.close()

    ok, reason = telegram_command_service.process_telegram_proposal_vote_command(
        lambda: _connect(db_path), _settings(), lambda *a, **kw: True, "alice", "/pvote 7 yes", telegram_user_id=42
    )
    assert (ok, reason) == (False, "proposal_closed")


def test_vote_callback_dispatches_pollvote_to_vote_command(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO members (username, telegram_user_id) VALUES ('alice', 42)")
    conn.execute("INSERT INTO polls (question, options_json, status) VALUES ('Snacks?', '[\"Yes\",\"No\"]', 'open')")
    conn.commit()
    conn.close()

    ok, reason = telegram_command_service.process_telegram_vote_callback(
        lambda: _connect(db_path),
        _settings(),
        lambda message: None,
        lambda *a, **kw: True,
        "alice",
        "pollvote:1:1",
        telegram_user_id=42,
    )

    assert (ok, reason) == (True, "ok")
    conn = _connect(db_path)
    row = conn.execute("SELECT option_index FROM poll_votes").fetchone()
    conn.close()
    assert row["option_index"] == 1


def test_vote_callback_dispatches_pvote_to_proposal_vote_command(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO members (id, username, telegram_user_id) VALUES (1, 'alice', 42)")
    conn.execute("INSERT INTO proposals (id, status) VALUES (7, 'active')")
    conn.commit()
    conn.close()
    recorded = []

    ok, reason = telegram_command_service.process_telegram_vote_callback(
        lambda: _connect(db_path),
        _settings(),
        lambda message: None,
        lambda proposal_id, member_id, vote, source: recorded.append((proposal_id, member_id, vote, source)) or True,
        "alice",
        "pvote:7:yes",
        telegram_user_id=42,
    )

    assert (ok, reason) == (True, "ok")
    assert recorded == [(7, 1, "in_favor", "telegram")]


def test_vote_callback_rejects_unrecognized_format(tmp_path):
    db_path = _make_db(tmp_path)
    ok, reason = telegram_command_service.process_telegram_vote_callback(
        lambda: _connect(db_path), _settings(), lambda message: None, lambda *a, **kw: True, "alice", "bogus:1"
    )
    assert (ok, reason) == (False, "invalid_format")
