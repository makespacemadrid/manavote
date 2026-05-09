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
