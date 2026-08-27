"""Outbound Telegram messaging and webhook registration with Telegram's Bot API.

`telegram_client_cls` is injected explicitly rather than imported directly, so tests that
replace `main_routes.TelegramClient` with a fake (`patch.object(main_routes, "TelegramClient",
FakeClient)`) keep intercepting every call made through these functions, the same way
`main_routes.py`'s wrappers re-read it fresh from the module on every call.
"""


def send_telegram_message(telegram_client_cls, bot_token, chat_id, thread_id, message, poll_id=None, options=None):
    client = telegram_client_cls(bot_token, chat_id, thread_id)
    if poll_id is not None and options is not None:
        return client.send_poll_message(message, poll_id, options)
    return client.send_message(message)


def send_telegram_admin_test_message(telegram_client_cls, bot_token, admin_id, message, poll_id=None, options=None):
    return send_telegram_message(telegram_client_cls, bot_token, admin_id, "", message, poll_id, options)


def sync_telegram_webhook(telegram_client_cls, bot_token, webhook_secret, base_url):
    if not bot_token or not webhook_secret or not base_url:
        return False
    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook/{webhook_secret}"
    client = telegram_client_cls(bot_token, "", "")
    return client.set_webhook(webhook_url)


def sync_telegram_webhook_on_startup(telegram_client_cls, bot_token, webhook_secret, get_base_url, logger):
    """Synchronize a configured bot webhook after the database is ready.

    Returning a small status value lets startup distinguish an intentionally
    unconfigured integration from a Telegram API failure.
    """
    if not bot_token or not webhook_secret:
        return "skipped"
    base_url = get_base_url().rstrip("/")
    if not base_url:
        logger.warning(
            "Telegram bot is configured but its Base URL is empty; webhook was not synchronized"
        )
        return "missing_base_url"
    if sync_telegram_webhook(telegram_client_cls, bot_token, webhook_secret, base_url):
        logger.info("Telegram webhook synchronized")
        return "synced"
    logger.warning("Telegram webhook synchronization failed")
    return "failed"
