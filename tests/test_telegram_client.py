import pathlib
import sys
import unittest
from unittest.mock import patch

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

if __name__ == "__main__":
    unittest.main()
