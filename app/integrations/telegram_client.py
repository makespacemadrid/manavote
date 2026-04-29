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
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except RequestException:
            return False
