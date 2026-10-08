from datetime import datetime, timezone


def log_admin_backup_event(
    logger,
    *,
    event,
    actor_id,
    backup_type,
    file_name=None,
    reason_code=None,
    status=None,
    pruned_count=None,
    file_size_bytes=None,
    error=None,
):
    logger.info(
        "event=%s actor_id=%s backup_type=%s file_name=%s reason_code=%s status=%s pruned_count=%s file_size_bytes=%s error=%s at=%s",
        event,
        actor_id,
        backup_type,
        file_name,
        reason_code,
        status,
        pruned_count,
        file_size_bytes,
        error,
        datetime.now(timezone.utc).isoformat(),
    )


def log_telegram_link_event(
    logger,
    *,
    event,
    actor_id=None,
    target_member_id=None,
    source=None,
    reason_code=None,
    status=None,
):
    logger.info(
        "event=%s actor_id=%s target_member_id=%s source=%s reason_code=%s status=%s at=%s",
        event,
        actor_id,
        target_member_id,
        source,
        reason_code,
        status,
        datetime.now(timezone.utc).isoformat(),
    )
