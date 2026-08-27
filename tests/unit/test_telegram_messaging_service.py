import logging

from app.services import telegram_messaging_service


class FakeTelegramClient:
    instances = []

    def __init__(self, bot_token, chat_id, thread_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.sent_messages = []
        self.sent_polls = []
        self.webhooks_set = []
        FakeTelegramClient.instances.append(self)

    def send_message(self, message):
        self.sent_messages.append(message)
        return True

    def send_poll_message(self, message, poll_id, options):
        self.sent_polls.append((message, poll_id, options))
        return True

    def set_webhook(self, url):
        self.webhooks_set.append(url)
        return True


def setup_function(_fn):
    FakeTelegramClient.instances = []


def test_send_telegram_message_uses_chat_and_thread():
    telegram_messaging_service.send_telegram_message(
        FakeTelegramClient, "token", "chat-1", "thread-1", "hello"
    )
    client = FakeTelegramClient.instances[0]
    assert (client.bot_token, client.chat_id, client.thread_id) == ("token", "chat-1", "thread-1")
    assert client.sent_messages == ["hello"]


def test_send_telegram_message_sends_poll_when_poll_id_and_options_given():
    telegram_messaging_service.send_telegram_message(
        FakeTelegramClient, "token", "chat-1", "thread-1", "poll text", poll_id=5, options=["a", "b"]
    )
    client = FakeTelegramClient.instances[0]
    assert client.sent_polls == [("poll text", 5, ["a", "b"])]
    assert client.sent_messages == []


def test_send_telegram_admin_test_message_uses_admin_id_and_no_thread():
    telegram_messaging_service.send_telegram_admin_test_message(
        FakeTelegramClient, "token", "admin-42", "ping"
    )
    client = FakeTelegramClient.instances[0]
    assert (client.chat_id, client.thread_id) == ("admin-42", "")
    assert client.sent_messages == ["ping"]


def test_sync_telegram_webhook_registers_expected_url():
    ok = telegram_messaging_service.sync_telegram_webhook(
        FakeTelegramClient, "token", "secret123", "https://example.com/"
    )
    assert ok is True
    client = FakeTelegramClient.instances[0]
    assert client.webhooks_set == ["https://example.com/telegram/webhook/secret123"]


def test_sync_telegram_webhook_returns_false_when_unconfigured():
    assert telegram_messaging_service.sync_telegram_webhook(FakeTelegramClient, "", "secret", "https://example.com") is False
    assert telegram_messaging_service.sync_telegram_webhook(FakeTelegramClient, "token", "", "https://example.com") is False
    assert telegram_messaging_service.sync_telegram_webhook(FakeTelegramClient, "token", "secret", "") is False
    assert FakeTelegramClient.instances == []


def test_sync_telegram_webhook_on_startup_skipped_when_unconfigured():
    logger = logging.getLogger("test")
    status = telegram_messaging_service.sync_telegram_webhook_on_startup(
        FakeTelegramClient, "", "", lambda: "https://example.com", logger
    )
    assert status == "skipped"


def test_sync_telegram_webhook_on_startup_missing_base_url():
    logger = logging.getLogger("test")
    status = telegram_messaging_service.sync_telegram_webhook_on_startup(
        FakeTelegramClient, "token", "secret", lambda: "", logger
    )
    assert status == "missing_base_url"


def test_sync_telegram_webhook_on_startup_synced():
    logger = logging.getLogger("test")
    status = telegram_messaging_service.sync_telegram_webhook_on_startup(
        FakeTelegramClient, "token", "secret", lambda: "https://example.com", logger
    )
    assert status == "synced"
    assert FakeTelegramClient.instances[0].webhooks_set == ["https://example.com/telegram/webhook/secret"]


def test_sync_telegram_webhook_on_startup_failed():
    class FailingClient(FakeTelegramClient):
        def set_webhook(self, url):
            self.webhooks_set.append(url)
            return False

    logger = logging.getLogger("test")
    status = telegram_messaging_service.sync_telegram_webhook_on_startup(
        FailingClient, "token", "secret", lambda: "https://example.com", logger
    )
    assert status == "failed"
