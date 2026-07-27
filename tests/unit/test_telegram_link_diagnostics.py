from app.services.telegram_link_diagnostics import LINKED_CONDITION_SQL, link_state_case_sql


def test_linked_condition_sql_mentions_required_fields():
    assert "telegram_user_id" in LINKED_CONDITION_SQL
    assert "telegram_username" not in LINKED_CONDITION_SQL


def test_link_state_case_sql_includes_all_states():
    sql = link_state_case_sql()
    for token in ("'linked'", "'missing_user_id'", "'unlinked'"):
        assert token in sql
    assert "'missing_username'" not in sql
