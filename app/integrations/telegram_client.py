import requests
from requests import RequestException


class TelegramClient:
    def __init__(self, bot_token: str, chat_id: str, thread_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.thread_id = (thread_id or "").strip()

    def _thread_id(self) -> int | None:
        if not self.thread_id:
            return None
        try:
            return int(self.thread_id)
        except ValueError:
            return None

    def send_message(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            payload = {"chat_id": self.chat_id, "text": message}
            thread_id = self._thread_id()
            if thread_id is not None:
                payload["message_thread_id"] = thread_id
            return self._telegram_ok(url, payload)
        except RequestException:
            return False

    def send_poll_message(self, message: str, poll_id: int, options: list[str]) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
            }
            thread_id = self._thread_id()
            if thread_id is not None:
                payload["message_thread_id"] = thread_id
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": "Vote", "callback_data": f"showvote:{poll_id}"}]
                ]
            }
            return self._telegram_ok(url, payload)
        except RequestException:
            return False

    def edit_message_with_vote_options(self, chat_id: str | int, message_id: int, poll_id: int, options: list[str]) -> bool:
        if not self.bot_token:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageReplyMarkup"
        try:
            payload = {
                "chat_id": str(chat_id),
                "message_id": message_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": option, "callback_data": f"pollvote:{poll_id}:{idx}"}]
                        for idx, option in enumerate(options)
                    ]
                }
            }
            return self._telegram_ok(url, payload)
        except RequestException:
            return False

    def answer_callback_query(self, callback_query_id: str, text: str) -> bool:
        if not self.bot_token or not callback_query_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        try:
            return self._telegram_ok(
                url, {"callback_query_id": callback_query_id, "text": text}
            )
        except RequestException:
            return False

    def _telegram_ok(self, url: str, payload: dict) -> bool:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            return False
        try:
            body = response.json()
            return bool(body.get("ok", False))
        except ValueError:
            return True

    def set_webhook(self, webhook_url: str) -> bool:
        if not self.bot_token or not webhook_url:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
        return self._telegram_ok(url, {"url": webhook_url})
