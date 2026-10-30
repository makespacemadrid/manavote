"""Behavioral checks for the audit's content, discovery and privacy changes."""
import sqlite3
from pathlib import Path

import pytest

from app.db.migrations import run_migrations
from app.services.content_service import render_member_markdown
from app.services.proposal_page_service import build_proposal_page
from app.services import feedback_service
from app.repositories.feedback_repo import FeedbackRepository


@pytest.fixture
def db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(Path('app/db/schema.sql').read_text())
    run_migrations(conn.cursor())
    conn.executemany("INSERT INTO members(id,username,password_hash) VALUES (?,?,'unused')", [(1,'Ada'),(2,'Bea')])
    conn.commit()
    yield conn
    conn.close()


def test_search_is_literal_unicode_aware_sorted_and_paginated(db):
    for number in range(25):
        db.execute("INSERT INTO proposals(title,description,amount,created_by,status) VALUES (?, 'workshop', ?,1,'active')", (f'ÑANDÚ 100%_{number}', number + 1))
    db.execute("INSERT INTO proposals(title,amount,created_by,status) VALUES ('100 other',2,1,'approved')")
    db.commit()
    first = build_proposal_page(db, member_id=1, filter_type='all', query='ñandú 100%_', sort='amount_asc')
    second = build_proposal_page(db, member_id=1, filter_type='all', query='ñandú 100%_', sort='amount_asc', page=2)
    assert first['matching_count'] == 25 and first['total_pages'] == 2
    assert [p['amount'] for p in first['proposals']] == list(range(1,21))
    assert [p['amount'] for p in second['proposals']] == list(range(21,26))
    assert build_proposal_page(db, member_id=1, query='nothing')['matching_count'] == 0
    # User input never becomes a SQL column/order expression.
    model = build_proposal_page(db, member_id=1, sort='amount; DROP TABLE proposals', page=-50)
    assert model['proposal_sort'] == 'newest' and model['page'] == 1
    assert db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0] == 26


def test_search_status_age_and_type_combine_without_changing_legacy_age(db):
    db.executemany("INSERT INTO proposals(title,amount,created_by,status,created_at,basic_supplies) VALUES (?, ?,1,?,?,?)", [
        ('Old approved',12,'approved','2000-01-01',1), ('Old active',12,'active','2000-01-01',1), ('Old expensive',70,'active','2000-01-01',0)])
    model = build_proposal_page(db, member_id=1, filter_type='approved', age='old', kind='basic')
    assert [p['title'] for p in model['proposals']] == ['Old approved']
    assert {p['title'] for p in build_proposal_page(db, member_id=1, filter_type='old')['proposals']} == {'Old active','Old expensive'}


@pytest.mark.parametrize('content', [
    '<script>alert(1)</script><p onclick="alert(2)">hello</p>',
    '<img src=x onerror=alert(1)><iframe src="https://example.org"></iframe>',
    '[open](javascript:alert%281%29)', '<a href="jav&#x61;script:alert(1)">open</a>',
    '<svg><a xlink:href="javascript:alert(1)">open</a></svg>',
    '<form action="https://example.org"><input name=password></form>',
])
def test_markdown_keeps_active_content_inert(content):
    rendered = render_member_markdown(content)
    assert '<script' not in rendered and '<img' not in rendered and '<iframe' not in rendered
    assert '<svg' not in rendered and '<form' not in rendered and '<input' not in rendered
    assert 'onclick=' not in rendered and 'href="javascript:' not in rendered


def test_markdown_preserves_normal_formatting_and_safe_links():
    rendered = render_member_markdown('## Parts\n\n**Important** [link](https://example.org)\n\n- one\n- two')
    assert '<h2>Parts</h2>' in rendered and '<strong>Important</strong>' in rendered
    assert '<a href="https://example.org">link</a>' in rendered and '<li>one</li>' in rendered


def test_feedback_history_is_owned_and_contains_only_public_details(db):
    feedback_id = feedback_service.submit_feedback(db, member_id=1, source='web', category='bug', message='Layout issue')
    feedback_service.submit_feedback(db, member_id=2, source='web', category='bug', message='Other member secret')
    feedback_service.manage_feedback(db, action='add_feedback_note', feedback_id=feedback_id, actor_id=2, is_admin=True, message='Private operator discussion')
    feedback_service.update_feedback_status(db, feedback_id=feedback_id, status='rejected', resolved_by=2, public_reason='Duplicate of #10')
    feedback_service.update_feedback_status(db, feedback_id=feedback_id, status='rejected', resolved_by=2, public_reason='Duplicate of #10')
    items = FeedbackRepository(db).for_member(1)
    assert len(items) == 1 and items[0]['public_reason'] == 'Duplicate of #10'
    assert [e['status'] for e in items[0]['history']] == ['new', 'rejected']
    assert 'Private operator discussion' not in str(items) and 'Other member secret' not in str(items)
    with pytest.raises(feedback_service.FeedbackValidationError):
        feedback_service.update_feedback_status(db, feedback_id=feedback_id, status='resolved', resolved_by=2, public_reason='x'*4001)
    assert FeedbackRepository(db).get(feedback_id)['status'] == 'rejected'
    feedback_service.manage_feedback(db, action='delete_feedback', feedback_id=feedback_id, actor_id=2, is_admin=True)
    assert db.execute('SELECT COUNT(*) FROM feedback_status_events WHERE feedback_id=?',(feedback_id,)).fetchone()[0] == 0
