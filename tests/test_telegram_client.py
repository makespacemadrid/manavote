import pathlib
import sys
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.integrations.telegram_client import TelegramClient


class TestTelegramClient(unittest.TestCase):
    @patch("app.integrations.telegram_client.requests.post")
    def test_send_message_requires_telegram_ok_true(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": False}
        client = TelegramClient("token", "-100123", "")

        sent = client.send_message("hello")

        self.assertFalse(sent)

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_photo_uses_public_url_and_preserves_topic_reply(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "7", reply_to_message_id=91)

        self.assertTrue(client.send_photo("https://vote.example/static/uploads/image.png"))

        self.assertTrue(mock_post.call_args.args[0].endswith("/sendPhoto"))
        self.assertEqual(
            mock_post.call_args.kwargs["json"],
            {
                "chat_id": "-100123",
                "photo": "https://vote.example/static/uploads/image.png",
                "message_thread_id": 7,
                "reply_parameters": {"message_id": 91, "allow_sending_without_reply": True},
            },
        )

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_message_with_id_returns_created_telegram_message_id(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "ok": True,
            "result": {"message_id": 456},
        }
        client = TelegramClient("token", "-100123", "7")

        message_id = client.send_message_with_id("🤔 Thinking…")

        self.assertEqual(message_id, 456)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message_thread_id"], 7)

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_message_anchors_forum_reply_to_incoming_message(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "7", reply_to_message_id=91)

        self.assertTrue(client.send_message("hello topic"))

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message_thread_id"], 7)
        self.assertEqual(
            payload["reply_parameters"],
            {"message_id": 91, "allow_sending_without_reply": True},
        )

    @patch("app.integrations.telegram_client.requests.post")
    def test_delete_message_uses_chat_and_temporary_message_id(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "")

        self.assertTrue(client.delete_message(456))
        self.assertTrue(mock_post.call_args.args[0].endswith("/deleteMessage"))
        self.assertEqual(
            mock_post.call_args.kwargs["json"],
            {"chat_id": "-100123", "message_id": 456},
        )

    @patch("app.integrations.telegram_client.requests.post")
    def test_delete_message_without_id_does_not_call_telegram(self, mock_post):
        client = TelegramClient("token", "-100123", "")

        self.assertFalse(client.delete_message(None))
        mock_post.assert_not_called()

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_message_with_id_handles_missing_result(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "")

        self.assertIsNone(client.send_message_with_id("Thinking"))

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_long_message_splits_oversized_assistant_reply(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "")

        sent = client.send_long_message("A" * 8000)

        self.assertTrue(sent)
        payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
        self.assertEqual([len(payload["text"]) for payload in payloads], [3900, 3900, 200])
        self.assertTrue(all(len(payload["text"]) <= 3900 for payload in payloads))

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_long_message_prefers_paragraph_boundary(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "")

        self.assertTrue(client.send_long_message(("A" * 3000) + "\n" + ("B" * 2000)))
        payloads = [call.kwargs["json"]["text"] for call in mock_post.call_args_list]
        self.assertEqual(payloads, ["A" * 3000, "B" * 2000])

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_long_message_stops_after_failed_chunk(self, mock_post):
        first = unittest.mock.Mock(status_code=200)
        first.json.return_value = {"ok": False}
        mock_post.return_value = first
        client = TelegramClient("token", "-100123", "")

        self.assertFalse(client.send_long_message("A" * 8000))
        self.assertEqual(mock_post.call_count, 1)

    @patch("app.integrations.telegram_client.requests.post")
    def test_send_poll_message_sets_vote_button_without_markdown_parse_mode(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "")

        sent = client.send_poll_message("*Question with _markdown_*", 9, ["Yes", "No"])

        self.assertTrue(sent)
        payload = mock_post.call_args.kwargs["json"]
        self.assertNotIn("parse_mode", payload)
        self.assertEqual(payload["reply_markup"]["inline_keyboard"][0][0]["text"], "Vote")
        self.assertEqual(payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "showvote:9")

    @patch("app.integrations.telegram_client.requests.post")
    def test_edit_message_with_vote_options_builds_inline_keyboard(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "")

        updated = client.edit_message_with_vote_options("-100123", 77, 3, ["One", "Two"])

        self.assertTrue(updated)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "pollvote:3:0")
        self.assertEqual(payload["reply_markup"]["inline_keyboard"][1][0]["callback_data"], "pollvote:3:1")


    @patch("app.integrations.telegram_client.requests.post")
    def test_send_proposal_vote_message_builds_yes_no_buttons(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        client = TelegramClient("token", "-100123", "")

        sent = client.send_proposal_vote_message("New proposal", 12)

        self.assertTrue(sent)
        payload = mock_post.call_args.kwargs["json"]
        kb = payload["reply_markup"]["inline_keyboard"]
        self.assertEqual(kb[0][0]["callback_data"], "pvote:12:yes")
        self.assertEqual(kb[1][0]["callback_data"], "pvote:12:no")

    @patch("app.integrations.telegram_client.requests.post")
    def test_set_webhook_handles_network_failure(self, mock_post):
        mock_post.side_effect = requests.RequestException("network unavailable")

        synced = TelegramClient("token", "", "").set_webhook("https://example.org/telegram/webhook/secret")

        self.assertFalse(synced)

if __name__ == "__main__":
    unittest.main()
