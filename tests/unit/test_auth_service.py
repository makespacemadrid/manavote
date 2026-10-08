import hashlib
import sqlite3
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

from app.db.migrations import run_migrations
from app.services import auth_service


@pytest.fixture
def connection():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript((Path(__file__).resolve().parents[2] / 'app/db/schema.sql').read_text())
    run_migrations(conn.cursor())
    yield conn
    conn.close()


def test_registration_duplicate_and_legacy_login_migration(connection):
    member_id = auth_service.register_member(connection, 'alice', 'secret')
    assert auth_service.register_member(connection, 'alice', 'different') is None
    assert auth_service.authenticate(connection, 'alice', 'wrong') is None
    assert auth_service.authenticate(connection, 'missing', 'secret') is None
    connection.execute('UPDATE members SET email = ?, password_hash = ? WHERE id = ?',
        ('Alice@example.org', hashlib.sha256(b'secret').hexdigest(), member_id))
    connection.commit()
    assert auth_service.authenticate(connection, 'ALICE@example.org', 'secret')['id'] == member_id
    assert check_password_hash(connection.execute('SELECT password_hash FROM members').fetchone()[0], 'secret')


def test_username_precedes_email_and_oidc_never_attaches_another_subject(connection):
    alice = auth_service.register_member(connection, 'alice', 'a')
    bob = auth_service.register_member(connection, 'bob', 'b')
    connection.execute('UPDATE members SET email = ?, oidc_sub = ? WHERE id = ?', ('alice', 'bob-sub', bob))
    connection.commit()
    assert auth_service.authenticate(connection, 'alice', 'a')['id'] == alice
    row = auth_service.upsert_oidc_member(connection, {'sub': 'new-sub', 'preferred_username': 'bob', 'email': 'alice'})
    assert row['id'] != bob and row['username'] == 'bob-2'


def test_oidc_email_attachment_role_sync_and_missing_telegram_claims(connection):
    member_id = auth_service.register_member(connection, 'alice', 'secret')
    connection.execute('UPDATE members SET email = ?, telegram_user_id = ?, telegram_username = ? WHERE id = ?',
        ('Alice@example.org', 123, 'alice_tg', member_id))
    connection.commit()
    row = auth_service.upsert_oidc_member(connection, {'sub': 'subject', 'email': 'alice@example.org', 'groups': ['admins']})
    assert row['id'] == member_id and row['is_admin'] == 1
    row = auth_service.upsert_oidc_member(connection, {'sub': 'subject', 'groups': []})
    assert row['is_admin'] == 0 and row['telegram_user_id'] == 123 and row['telegram_username'] == 'alice_tg'
    assert row['email'] == 'alice@example.org'


@pytest.mark.parametrize('new,confirm,error', [('', '', 'All fields are required'), ('abcd', 'different', 'New passwords do not match'), ('abc', 'abc', 'Password must be at least 4 characters')])
def test_password_validation_does_not_write(connection, new, confirm, error):
    member_id = auth_service.register_member(connection, 'alice', 'original')
    assert auth_service.change_password(connection, member_id, new, confirm) == error
    assert auth_service.authenticate(connection, 'alice', 'original')


def test_password_change_and_email_immutability(connection):
    member_id = auth_service.register_member(connection, 'alice', 'original')
    assert auth_service.change_password(connection, member_id, 'updated', 'updated') is None
    assert auth_service.authenticate(connection, 'alice', 'updated')
    assert auth_service.add_member_email(connection, member_id, 'wrong') == 'Enter a valid email address.'
    assert auth_service.add_member_email(connection, member_id, ' Alice@example.org ') is None
    other = auth_service.register_member(connection, 'bob', 'secret')
    assert auth_service.add_member_email(connection, other, 'ALICE@example.org') == 'That email address is already in use.'
    assert auth_service.add_member_email(connection, member_id, 'new@example.org') == 'Your email address cannot be changed once it has been added.'
