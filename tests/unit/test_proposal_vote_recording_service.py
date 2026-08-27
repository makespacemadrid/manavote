import logging
import sqlite3

from app.services import proposal_vote_recording_service


def _make_db(tmp_path):
    db_path = str(tmp_path / "vote_recording.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, status TEXT)")
    conn.execute(
        "CREATE TABLE votes (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id INTEGER, member_id INTEGER, vote TEXT, UNIQUE(proposal_id, member_id))"
    )
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


def test_record_proposal_vote_rejected_when_channel_disabled():
    logger = logging.getLogger("test")
    calls = []

    ok = proposal_vote_recording_service.record_proposal_vote(
        lambda: (_ for _ in ()).throw(AssertionError("get_db should not be called")),
        _settings({"proposal_vote_mode": "web_only"}),
        lambda proposal_id: calls.append(proposal_id),
        logger,
        1,
        2,
        "in_favor",
        source="telegram",
    )

    assert ok is False
    assert calls == []


def test_record_proposal_vote_records_and_triggers_processing_for_active_proposal(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO proposals (id, status) VALUES (1, 'active')")
    conn.commit()
    conn.close()

    processed = []
    logger = logging.getLogger("test")

    ok = proposal_vote_recording_service.record_proposal_vote(
        lambda: _connect(db_path), _settings(), lambda proposal_id: processed.append(proposal_id), logger, 1, 2, "in_favor"
    )

    assert ok is True
    assert processed == [1]
    conn = _connect(db_path)
    row = conn.execute("SELECT vote FROM votes WHERE proposal_id = 1 AND member_id = 2").fetchone()
    conn.close()
    assert row["vote"] == "in_favor"


def test_record_proposal_vote_skips_processing_for_non_active_proposal(tmp_path):
    db_path = _make_db(tmp_path)
    conn = _connect(db_path)
    conn.execute("INSERT INTO proposals (id, status) VALUES (1, 'approved')")
    conn.commit()
    conn.close()

    processed = []
    logger = logging.getLogger("test")

    ok = proposal_vote_recording_service.record_proposal_vote(
        lambda: _connect(db_path), _settings(), lambda proposal_id: processed.append(proposal_id), logger, 1, 2, "against"
    )

    assert ok is True
    assert processed == []


def test_log_proposal_vote_event_includes_current_mode(caplog):
    logger = logging.getLogger("test")

    with caplog.at_level("INFO", logger="test"):
        proposal_vote_recording_service.log_proposal_vote_event(
            logger,
            _settings({"proposal_vote_mode": "telegram_only"}),
            event="proposal_vote_accepted",
            source="telegram",
            proposal_id=10,
            member_id=22,
            vote="in_favor",
            reason_code="ok",
            latency_ms=1.5,
        )

    assert [record.message for record in caplog.records] == [
        "event=proposal_vote_accepted source=telegram mode=telegram_only proposal_id=10 member_id=22 "
        "vote=in_favor reason_code=ok latency_ms=1.5"
    ]
