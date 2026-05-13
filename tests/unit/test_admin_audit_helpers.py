import logging

from app.web.routes.helpers.admin_audit_helpers import log_telegram_link_event


def test_log_telegram_link_event_emits_expected_fields(caplog):
    logger = logging.getLogger("test.telegram.audit")
    with caplog.at_level(logging.INFO):
        log_telegram_link_event(
            logger,
            event="member_telegram_unlink",
            actor_id=1,
            target_member_id=1,
            source="member_settings",
            reason_code="self_unlink",
            status="success",
        )
    msg = caplog.records[-1].getMessage()
    assert "event=member_telegram_unlink" in msg
    assert "actor_id=1" in msg
    assert "target_member_id=1" in msg
    assert "source=member_settings" in msg
