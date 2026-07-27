LINKED_CONDITION_SQL = "telegram_user_id IS NOT NULL"


def link_state_case_sql() -> str:
    return """
    CASE
        WHEN telegram_user_id IS NOT NULL THEN 'linked'
        WHEN telegram_user_id IS NULL AND telegram_username IS NOT NULL AND telegram_username != '' THEN 'missing_user_id'
        ELSE 'unlinked'
    END
    """
