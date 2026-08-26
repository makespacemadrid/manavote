import requests
from requests import RequestException


class TelegramClient:
    MESSAGE_CHUNK_SIZE = 3900

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        thread_id: str = "",
        reply_to_message_id: int | None = None,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.thread_id = (thread_id or "").strip()
        self.reply_to_message_id = reply_to_message_id

    def _thread_id(self) -> int | None:
        if not self.thread_id:
            return None
        try:
            return int(self.thread_id)
        except ValueError:
            return None

    def _message_payload(self, message: str) -> dict:
        """Build a payload that Telegram can reliably anchor to a forum topic."""
        payload = {"chat_id": self.chat_id, "text": message}
        thread_id = self._thread_id()
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        if self.reply_to_message_id is not None:
            try:
                reply_message_id = int(self.reply_to_message_id)
            except (TypeError, ValueError):
                pass
            else:
                payload["reply_parameters"] = {
                    "message_id": reply_message_id,
                    "allow_sending_without_reply": True,
                }
        return payload

    def send_message(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            payload = self._message_payload(message)
            return self._telegram_ok(url, payload)
        except RequestException:
            return False

    def send_message_with_id(self, message: str) -> int | None:
        """Send a message and return its Telegram message ID when available."""
        if not self.bot_token or not self.chat_id:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = self._message_payload(message)
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                return None
            body = response.json()
            if not body.get("ok"):
                return None
            message_id = (body.get("result") or {}).get("message_id")
            return int(message_id) if message_id is not None else None
        except (RequestException, TypeError, ValueError):
            return None

    def delete_message(self, message_id: int | None) -> bool:
        """Delete a previously sent message, if Telegram returned an ID for it."""
        if not self.bot_token or not self.chat_id or message_id is None:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/deleteMessage"
        try:
            return self._telegram_ok(
                url,
                {"chat_id": self.chat_id, "message_id": int(message_id)},
            )
        except (RequestException, TypeError, ValueError):
            return False

    @classmethod
    def _message_chunks(cls, message: str) -> list[str]:
        """Split text below Telegram's limit, preferring readable boundaries."""
        remaining = str(message or "")
        if not remaining:
            return []
        chunks = []
        while len(remaining) > cls.MESSAGE_CHUNK_SIZE:
            boundary = remaining.rfind("\n", 0, cls.MESSAGE_CHUNK_SIZE + 1)
            if boundary < cls.MESSAGE_CHUNK_SIZE // 2:
                boundary = remaining.rfind(" ", 0, cls.MESSAGE_CHUNK_SIZE + 1)
            if boundary < cls.MESSAGE_CHUNK_SIZE // 2:
                boundary = cls.MESSAGE_CHUNK_SIZE
            chunks.append(remaining[:boundary].rstrip())
            remaining = remaining[boundary:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks

    def send_long_message(self, message: str) -> bool:
        """Send every chunk of a potentially long assistant response."""
        chunks = self._message_chunks(message)
        if not chunks:
            return False
        return all(self.send_message(chunk) for chunk in chunks)

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


    def send_proposal_vote_message(self, message: str, proposal_id: int) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "✅ Yes", "callback_data": f"pvote:{proposal_id}:yes"}],
                        [{"text": "❌ No", "callback_data": f"pvote:{proposal_id}:no"}],
                    ]
                },
            }
            thread_id = self._thread_id()
            if thread_id is not None:
                payload["message_thread_id"] = thread_id
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
        try:
            return self._telegram_ok(url, {"url": webhook_url})
        except RequestException:
            return False
