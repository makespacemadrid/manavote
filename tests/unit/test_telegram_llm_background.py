from unittest.mock import patch

from app.web.routes import main_routes


def test_background_response_sends_assistant_text():
    context = {"text": "budget?", "telegram_user_id": 5, "chat_id": 99, "chat_type": "private"}
    with patch.object(main_routes, "TELEGRAM_BOT_TOKEN", "token"), patch.object(
        main_routes, "process_telegram_assistant_message", return_value="€250"
    ), patch.object(
        main_routes.TelegramClient, "send_message", return_value=True
    ) as send:
        main_routes._send_telegram_assistant_response(context)
    send.assert_called_once_with("€250")


def test_background_response_does_not_send_empty_result():
    context = {"text": "hello", "telegram_user_id": 5, "chat_id": 99, "chat_type": "private"}
    with patch.object(main_routes, "process_telegram_assistant_message", return_value=None), patch.object(
        main_routes.TelegramClient, "send_message"
    ) as send:
        main_routes._send_telegram_assistant_response(context)
    send.assert_not_called()


def test_webhook_acknowledges_before_submitting_assistant_work(monkeypatch):
    submitted = []

    class Executor:
        def submit(self, function, context):
            submitted.append((function, context))

    monkeypatch.setattr(main_routes, "TELEGRAM_WEBHOOK_SECRET", "hook")
    monkeypatch.setattr(main_routes, "TELEGRAM_LLM_API_KEY", "llm-key")
    monkeypatch.setattr(main_routes, "TELEGRAM_LLM_MODEL", "model")
    monkeypatch.setattr(main_routes, "telegram_assistant_executor", Executor())
    monkeypatch.setattr(main_routes, "telegram_assistant_updates", main_routes.UpdateDeduplicator())
    payload = {
        "update_id": 55,
        "message": {"text": "What is the budget?", "from": {"id": 5}, "chat": {"id": 99, "type": "private"}},
    }

    with main_routes.app.test_request_context("/telegram/webhook/hook", method="POST", json=payload):
        response = main_routes.telegram_webhook("hook")
    with main_routes.app.test_request_context("/telegram/webhook/hook", method="POST", json=payload):
        duplicate = main_routes.telegram_webhook("hook")

    assert response == ({"ok": True}, 200)
    assert duplicate == ({"ok": True}, 200)
    assert len(submitted) == 1
    assert submitted[0][1]["text"] == "What is the budget?"
