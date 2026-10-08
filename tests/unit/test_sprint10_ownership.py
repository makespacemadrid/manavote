"""Boundary guards and direct regression coverage for the remaining Sprint 10 owners."""
import ast
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.db.initialization import initialize_database
from app.repositories.budget_repo import BudgetRepository
from app.repositories.group_purchase_repo import GroupPurchaseRepository
from app.repositories.poll_repo import PollRepository
from app.repositories.settings_repo import SettingsRepository
from app.services import admin_actions_service as admin, admin_page_service
from app.services import group_purchase_service as groups, poll_page_service as polls
from app.services import proposal_actions_service as proposals
from app.services.budget_service import calculate_min_backers
from app.services.proposal_page_service import build_proposal_detail

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'ownership.db'
    initialize_database(str(path), testing=True, production=False, logger=Mock())
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO members (id, username, password_hash) VALUES (2, 'other', 'unused')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def dependencies(db, tmp_path):
    budget, settings = BudgetRepository(db), SettingsRepository(db)
    return admin.AdminDependencies(
        get_db=lambda: db, get_current_budget=budget.current_budget,
        get_setting_float=lambda key, default: float(settings.get_value(key, default)),
        get_setting_value=settings.get_value, check_over_budget_proposals=Mock(),
        sync_telegram_webhook=Mock(return_value=True), build_poll_results_message=Mock(return_value='results'),
        send_telegram_message=Mock(return_value=True), send_telegram_admin_test_message=Mock(return_value=True),
        db_path=str(tmp_path / 'ownership.db'), upload_folder=str(tmp_path), telegram_admin_id='123', logger=Mock(),
    )


def run_admin(db, dependencies, **data):
    return admin.apply_admin_action(db, data=data, actor_id=1, is_admin=True, dependencies=dependencies)


def create_group(db):
    return groups.create_purchase(db, title='Components', description='', deadline='', product_url='',
        image_filename=None, payment_method='', member_id=1, components=[('A', 10), ('B', 20)], shared_costs=[('Shipping', 9)])


def test_route_modules_cannot_execute_sql():
    violations = []
    for path in (ROOT / 'app/web/routes').glob('*_routes.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {'execute', 'executemany', 'executescript'}:
                violations.append(f'{path.name}:{node.lineno}')
    assert not violations, violations


def test_repositories_do_not_import_service_owners():
    for path in (ROOT / 'app/repositories').glob('*.py'):
        tree = ast.parse(path.read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert all(not (m or '').startswith(('app.services', 'app.web')) for m in imports), path.name


@pytest.mark.parametrize('name', ['admin_actions_service', 'admin_page_service', 'group_purchase_service',
    'poll_page_service', 'proposal_actions_service', 'proposal_page_service', 'auth_service'])
def test_extracted_services_do_not_depend_on_web_context(name):
    tree = ast.parse((ROOT / 'app/services' / f'{name}.py').read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(not (m or '').startswith(('flask', 'app.web')) for m in imports)


def test_admin_self_protection_and_service_role_gate(db, dependencies):
    with pytest.raises(PermissionError):
        admin.apply_admin_action(db, data={'action': 'remove_member', 'member_id': '2'}, actor_id=2, is_admin=False, dependencies=dependencies)
    assert run_admin(db, dependencies, action='remove_member', member_id='1')[0] == [("You can't remove yourself", 'error')]
    assert run_admin(db, dependencies, action='toggle_admin', member_id='1')[0] == [("You can't change your own admin role", 'error')]
    assert db.execute('SELECT is_admin FROM members WHERE id = 1').fetchone()[0] == 1
    assert db.execute('SELECT COUNT(*) FROM members').fetchone()[0] == 2


def test_admin_identity_update_returns_session_change_without_web_context(db, dependencies):
    messages, username = run_admin(db, dependencies, action='edit_member_identity', member_id='1', username='renamed', email='Admin@example.org')
    assert username == 'renamed' and messages == [('Member account updated!', 'success')]
    assert db.execute('SELECT email FROM members WHERE id = 1').fetchone()[0] == 'admin@example.org'
    assert run_admin(db, dependencies, action='edit_member_identity', member_id='2', username='renamed')[0] == [('Username or email already exists', 'error')]


@pytest.mark.parametrize('amount,calls', [('20', 1), ('-20', 0)])
def test_admin_budget_reprocessing_depends_on_sign(db, dependencies, amount, calls):
    run_admin(db, dependencies, action='add_budget', amount=amount, description='test')
    assert dependencies.check_over_budget_proposals.call_count == calls
    assert BudgetRepository(db).current_budget() == 300 + float(amount)
    assert float(SettingsRepository(db).get_value('current_budget')) == 300 + float(amount)


def test_admin_budget_write_failure_rolls_back_setting_and_never_reprocesses(db, dependencies):
    db.execute("CREATE TRIGGER stop_log BEFORE INSERT ON activity_log BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    db.commit()
    with pytest.raises(sqlite3.IntegrityError, match='blocked'):
        run_admin(db, dependencies, action='add_budget', amount='20', description='test')
    assert BudgetRepository(db).current_budget() == 300
    assert SettingsRepository(db).get_value('current_budget') == '300'
    dependencies.check_over_budget_proposals.assert_not_called()


def test_admin_poll_create_send_close_delete_preserves_side_effects(db, dependencies):
    messages, _ = run_admin(db, dependencies, action='create_poll', question='Choose a room?', options='A\nB', closes_at='2099-01-01T12:00', allow_multiple='on')
    assert messages == [('Poll created!', 'success')]
    poll = db.execute('SELECT * FROM polls').fetchone()
    assert poll['allow_multiple'] == 1
    dependencies.send_telegram_message.assert_called_once()
    run_admin(db, dependencies, action='send_poll_telegram_test', poll_id=str(poll['id']))
    dependencies.send_telegram_admin_test_message.assert_called_once()
    run_admin(db, dependencies, action='close_poll', poll_id=str(poll['id']))
    assert db.execute('SELECT status FROM polls').fetchone()[0] == 'closed'
    assert dependencies.send_telegram_message.call_args.args == ('results',)
    run_admin(db, dependencies, action='delete_poll', poll_id=str(poll['id']))
    assert db.execute('SELECT COUNT(*) FROM polls').fetchone()[0] == 0
    assert run_admin(db, dependencies, action='delete_poll', poll_id=str(poll['id']))[0] == [('Poll not found', 'error')]


def test_admin_page_budget_history_and_member_statistics(db, dependencies, monkeypatch, tmp_path):
    from app.services import backup_service
    monkeypatch.setattr(backup_service, 'BACKUP_ROOT', str(tmp_path / 'backups'))
    run_admin(db, dependencies, action='add_budget', amount='-20', description='expense')
    model = admin_page_service.build_admin_page(db, db_path=dependencies.db_path,
        get_thresholds=SettingsRepository(db).get_thresholds, is_registration_enabled=lambda: True,
        get_current_budget=BudgetRepository(db).current_budget, logger=Mock())
    assert [r['balance'] for r in model['budget_history']] == [280, 300]
    assert len(model['members']) == len(model['member_stats']) == len(model['member_poll_stats']) == 2
    assert model['current_timezone'] == 'Europe/Madrid'


def test_group_debts_and_quantity_rules_are_service_owned(db):
    purchase_id = create_group(db)
    components = GroupPurchaseRepository(db).components(purchase_id)
    groups.set_quantity(db, purchase_id=purchase_id, component_id=components[0]['id'], member_id=1, quantity=1)
    groups.set_quantity(db, purchase_id=purchase_id, component_id=components[1]['id'], member_id=2, quantity=1)
    purchase = groups.build_purchase_page(db, 2)[0]
    assert [d['amount_owed'] for d in purchase['debts']] == [13, 26]
    assert purchase['components'][1]['user_quantity'] == 1
    groups.update_payment(db, purchase_id=purchase_id, member_id=2, actor_id=1, received=True)
    assert groups.build_purchase_page(db, 2)[0]['debts'][1]['received_at'] is not None
    with pytest.raises(ValueError, match='Payment cannot be updated'):
        groups.update_payment(db, purchase_id=purchase_id, member_id=1, actor_id=2, received=True)
    with pytest.raises(ValueError, match='Invalid status change'):
        groups.update_status(db, purchase_id=purchase_id, member_id=2, status='ordered')
    groups.update_status(db, purchase_id=purchase_id, member_id=1, status='ordered')
    with pytest.raises(ValueError, match='Component not found'):
        groups.set_quantity(db, purchase_id=purchase_id, component_id=components[0]['id'], member_id=1, quantity=0)
    groups.update_status(db, purchase_id=purchase_id, member_id=1, status='received')


def test_group_delete_rolls_back_all_dependents_on_failure(db):
    purchase_id = create_group(db)
    component_id = GroupPurchaseRepository(db).components(purchase_id)[0]['id']
    groups.set_quantity(db, purchase_id=purchase_id, component_id=component_id, member_id=2, quantity=1)
    groups.update_payment(db, purchase_id=purchase_id, member_id=2, actor_id=1, received=True)
    db.execute("CREATE TRIGGER stop_group BEFORE DELETE ON group_purchases BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    db.commit()
    with pytest.raises(sqlite3.IntegrityError, match='blocked'):
        groups.delete_purchase(db, purchase_id=purchase_id, member_id=2, is_admin=True)
    for table, count in [('group_purchases', 1), ('group_purchase_components', 2), ('group_purchase_shared_costs', 1), ('group_purchase_quantities', 1), ('group_purchase_payments', 1)]:
        assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == count
    db.execute('DROP TRIGGER stop_group')
    db.commit()
    groups.delete_purchase(db, purchase_id=purchase_id, member_id=2, is_admin=True)
    assert db.execute('SELECT COUNT(*) FROM group_purchase_quantities').fetchone()[0] == 0


def test_poll_page_additive_votes_clear_and_distinct_voters(db):
    poll_id = PollRepository(db).create('Choose a room?', ['A', 'B'], 1, True)
    kwargs = dict(poll_id=poll_id, member_id=1, clear_vote=False, single_index=0, logger=Mock())
    assert polls.vote_on_page(db, option_indexes=['0', '1'], **kwargs) == ('Poll vote recorded!', 'success')
    polls.vote_on_page(db, option_indexes=['0'], **kwargs)
    model, messages = polls.build_poll_page(db, member_id=1, logger=Mock())
    assert not messages
    assert model['polls'][0]['counts'] == [1, 1] and model['polls'][0]['total_voters'] == 1
    assert polls.vote_on_page(db, option_indexes=['bad'], **kwargs) == ('Invalid poll option', 'error')
    assert polls.vote_on_page(db, option_indexes=[], **{**kwargs, 'clear_vote': True}) == ('Your votes were cleared', 'success')
    assert polls.build_poll_page(db, member_id=1, logger=Mock())[0]['polls'][0]['user_votes'] == []


def test_poll_page_lookup_failure_returns_translated_error_without_writes(db, monkeypatch):
    def fail(*_args):
        raise sqlite3.OperationalError('missing')
    monkeypatch.setattr(PollRepository, 'get_by_id', fail)
    assert polls.vote_on_page(db, poll_id=1, member_id=1, clear_vote=False, option_indexes=['0'], single_index=0, logger=Mock()) == ('Polls are temporarily unavailable', 'error')


def test_proposal_creation_edit_autoflag_and_detail_have_direct_contract(db):
    processor = Mock()
    proposal_id, creator = proposals.create_web_proposal(db, title='Item', description='text', amount=25,
        url='', image_filename=None, member_id=1, basic_supplies=1, process_proposal=processor)
    assert creator == 'admin'
    processor.assert_called_once_with(proposal_id)
    with pytest.raises(proposals.ProposalActionError, match='proposal_owner_required'):
        proposals.get_proposal_for_web_edit(db, proposal_id=proposal_id, member_id=2, is_admin=False)
    proposals.update_web_proposal(db, proposal_id=proposal_id, member_id=2, is_admin=True,
        title='Revised', description='text', amount=30, url='', image_filename=None, basic_supplies=1)
    model = build_proposal_detail(db, proposal_id=proposal_id, member_id=1,
        get_member_count=lambda: 2, get_current_budget=BudgetRepository(db).current_budget,
        get_thresholds=SettingsRepository(db).get_thresholds, calculate_min_backers=calculate_min_backers,
        get_vote_counts=lambda cursor, proposal_id: (1, 0))
    assert model['proposal']['title'] == 'Revised' and model['proposal']['basic_supplies'] == 0
    assert model['user_vote'] == 'in_favor' and len(model['comments']) == 2


@pytest.mark.parametrize('data', [
    {'action': action} for action in ['add_member', 'edit_member_identity', 'remove_member', 'toggle_admin', 'unlink_telegram', 'add_budget']
] + [{'action': 'add_member', 'username': 'alice'}, {'action': 'add_budget', 'amount': '10'}])
def test_admin_missing_required_form_fields_remain_http_400(monkeypatch, data):
    from app import app
    from app.web.routes import main_routes
    connection = Mock()
    monkeypatch.setitem(app.config, 'TESTING', True)
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(main_routes, 'ensure_db_ready', lambda: None)
    monkeypatch.setattr(main_routes, 'get_db', lambda: connection)
    monkeypatch.setattr(main_routes, 'close_expired_polls', lambda _connection: [])
    use_case = Mock()
    monkeypatch.setattr(admin, 'apply_admin_action', use_case)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(member_id=1, is_admin=True, username='admin')
    assert client.post('/admin', data=data).status_code == 400
    use_case.assert_not_called()
    connection.close.assert_called_once_with()
