"""End-to-end Flask-level contract tests for the Telegram natural-language webhook path.

Unlike tests/unit/test_telegram_agent.py (which calls telegram_agent.answer() directly)
and the deterministic-command coverage in test_app_functionality.py, these tests drive
the actual POST /telegram/webhook/<secret> route so the wiring between the webhook
handler, the database-backed allowlist, the bounded executor, the thinking-message
lifecycle, and telegram_agent itself is exercised together.
"""

import itertools
import json
import os
import pathlib
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app as budget_app
import app.mcp_server as real_mcp_server
from app.integrations import telegram_agent
from app.web.routes import main_routes


# The webhook's update-ID deduplicator persists to a shared, session-wide SQLite table
# (it must survive process restarts), so fixed literal IDs would collide with prior test
# runs against the same database file. Derive a fresh, never-repeating base per test run.
_unique_id_counter = itertools.count(int(time.time() * 1000))


def _unique_id():
    return next(_unique_id_counter)


class FakeModelResponse:
    def __init__(self, message):
        self.message = message

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": self.message}]}


class RecordingTelegramClient:
    """Stands in for main_routes.TelegramClient so no real Telegram HTTP happens."""

    instances = []
    next_thinking_message_id = 555

    def __init__(self, bot_token, chat_id, thread_id="", reply_to_message_id=None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.reply_to_message_id = reply_to_message_id
        self.sent_messages = []
        self.long_messages = []
        self.deleted_message_ids = []
        self.sent_photos = []
        RecordingTelegramClient.instances.append(self)

    def send_message_with_id(self, message):
        self.sent_messages.append(message)
        return RecordingTelegramClient.next_thinking_message_id

    def send_long_message(self, message):
        self.long_messages.append(message)
        return True

    def send_photo(self, image_url, caption=None):
        self.sent_photos.append((image_url, caption))
        return True

    def send_message(self, message):
        self.sent_messages.append(message)
        return True

    def delete_message(self, message_id):
        self.deleted_message_ids.append(message_id)
        return True

    def send_proposal_vote_message(self, message, proposal_id):
        self.sent_messages.append(message)
        return True


class SyncExecutor:
    """Runs submitted work inline so the test can assert on it without polling a thread."""

    def __init__(self, reject=False):
        self.reject = reject
        self.submitted = 0

    def submit(self, function, *args, **kwargs):
        if self.reject:
            return None
        self.submitted += 1
        function(*args, **kwargs)
        return object()


class TestTelegramNaturalLanguageWebhook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        RecordingTelegramClient.instances = []
        self._telegram_client_patch = patch.object(main_routes, "TelegramClient", RecordingTelegramClient)
        self._telegram_client_patch.start()

        self._old_bot_token = main_routes.TELEGRAM_BOT_TOKEN
        self._old_webhook_secret = main_routes.TELEGRAM_WEBHOOK_SECRET
        self._old_bot_username = main_routes.TELEGRAM_BOT_USERNAME
        self._old_chat_id = main_routes.TELEGRAM_CHAT_ID
        self._old_thread_id = main_routes.TELEGRAM_THREAD_ID
        self._old_executor = main_routes._telegram_agent_executor
        self._old_mcp_api_key = real_mcp_server.MCP_API_KEY
        self._old_ocabra_url = os.environ.get("OCABRA_CHAT_URL")
        os.environ["OCABRA_CHAT_URL"] = "https://ocabra.example/v1/chat/completions"

        main_routes.TELEGRAM_BOT_TOKEN = "test-bot-token"
        main_routes.TELEGRAM_WEBHOOK_SECRET = "nl-hook-secret"
        main_routes.TELEGRAM_BOT_USERNAME = ""
        main_routes.TELEGRAM_CHAT_ID = ""
        main_routes.TELEGRAM_THREAD_ID = ""
        main_routes._telegram_agent_executor = SyncExecutor()
        real_mcp_server.MCP_API_KEY = "test-mcp-key"

        conn = budget_app.get_db()
        conn.execute(
            "UPDATE members SET telegram_username = NULL, telegram_user_id = NULL WHERE username = 'admin'"
        )
        conn.commit()
        conn.close()

        telegram_agent.configure_pending_action_store(None)
        telegram_agent.configure_history_store(None)

    def tearDown(self):
        self._telegram_client_patch.stop()
        main_routes.TELEGRAM_BOT_TOKEN = self._old_bot_token
        main_routes.TELEGRAM_WEBHOOK_SECRET = self._old_webhook_secret
        main_routes.TELEGRAM_BOT_USERNAME = self._old_bot_username
        main_routes.TELEGRAM_CHAT_ID = self._old_chat_id
        main_routes.TELEGRAM_THREAD_ID = self._old_thread_id
        main_routes._telegram_agent_executor = self._old_executor
        real_mcp_server.MCP_API_KEY = self._old_mcp_api_key
        if self._old_ocabra_url is None:
            os.environ.pop("OCABRA_CHAT_URL", None)
        else:
            os.environ["OCABRA_CHAT_URL"] = self._old_ocabra_url
        telegram_agent.configure_pending_action_store(None)
        telegram_agent.configure_history_store(None)

    def _link_member(self, member_id, telegram_user_id, is_admin=None):
        conn = budget_app.get_db()
        if is_admin is None:
            conn.execute(
                "UPDATE members SET telegram_user_id = ? WHERE id = ?", (telegram_user_id, member_id)
            )
        else:
            conn.execute(
                "UPDATE members SET telegram_user_id = ?, is_admin = ? WHERE id = ?",
                (telegram_user_id, 1 if is_admin else 0, member_id),
            )
        conn.commit()
        conn.close()

    def _post_message(self, text, telegram_user_id, update_id, message_id=1):
        return self.client.post(
            "/telegram/webhook/nl-hook-secret",
            json={
                "update_id": update_id,
                "message": {
                    "message_id": message_id,
                    "text": text,
                    "from": {"id": telegram_user_id, "username": f"user{telegram_user_id}"},
                    "chat": {"id": telegram_user_id, "type": "private"},
                },
            },
        )

    def test_unlinked_sender_is_ignored_without_enqueueing_work(self):
        response = self._post_message("What's our budget?", telegram_user_id=_unique_id(), update_id=_unique_id())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RecordingTelegramClient.instances, [])
        self.assertEqual(main_routes._telegram_agent_executor.submitted, 0)

    def test_linked_sender_gets_thinking_message_tool_call_and_final_reply(self):
        telegram_user_id = _unique_id()
        update_id = _unique_id()
        self._link_member(1, telegram_user_id)
        responses = iter(
            [
                FakeModelResponse(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "current_budget", "arguments": "{}"},
                            }
                        ],
                    }
                ),
                FakeModelResponse({"role": "assistant", "content": "The current budget is €300."}),
            ]
        )
        with self.assertLogs(main_routes.app.logger, level="INFO") as logs:
            with patch.object(telegram_agent.requests, "post", lambda *_a, **_kw: next(responses)):
                response = self._post_message(
                    "What's our budget?", telegram_user_id=telegram_user_id, update_id=update_id
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(RecordingTelegramClient.instances), 1)
        client = RecordingTelegramClient.instances[0]
        self.assertIn("🤔 Thinking…", client.sent_messages)
        self.assertEqual(client.deleted_message_ids, [RecordingTelegramClient.next_thinking_message_id])
        self.assertEqual(len(client.long_messages), 1)
        self.assertIn("300", client.long_messages[0])
        job_logs = "\n".join(logs.output)
        self.assertIn(f'"update_id": {update_id}', job_logs)
        self.assertIn(f'"chat_id": {telegram_user_id}', job_logs)
        self.assertIn('"actor_member_id": 1', job_logs)
        self.assertIn('"queue_wait_ms":', job_logs)
        self.assertIn('"model_latency_ms":', job_logs)
        self.assertIn('"tool_name": "current_budget"', job_logs)
        self.assertIn('"reason_code": "completed"', job_logs)

    def test_specific_proposal_request_returns_public_detail_and_image_urls(self):
        telegram_user_id = _unique_id()
        self._link_member(1, telegram_user_id)
        conn = budget_app.get_db()
        previous_url_row = conn.execute("SELECT value FROM settings WHERE key = 'url'").fetchone()
        previous_url = previous_url_row["value"] if previous_url_row else None
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('url', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("https://vote.example/",),
        )
        cursor = conn.execute(
            "INSERT INTO proposals "
            "(title, description, amount, url, image_filename, created_by, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "Telegram resource contract",
                "Proposal used to verify public links",
                42,
                "https://vendor.example/item",
                "telegram image.png",
                1,
                "active",
            ),
        )
        proposal_id = cursor.lastrowid
        conn.commit()
        conn.close()

        model_payloads = []

        def fake_post(*_args, **kwargs):
            payload = kwargs["json"]
            model_payloads.append(payload)
            if len(model_payloads) == 1:
                return FakeModelResponse(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-proposal-links",
                                "type": "function",
                                "function": {
                                    "name": "list_proposals",
                                    "arguments": json.dumps({"proposal_id": proposal_id}),
                                },
                            }
                        ],
                    }
                )
            tool_payload = json.loads(payload["messages"][-1]["content"])
            proposal = tool_payload["proposals"][0]
            return FakeModelResponse(
                {
                    "role": "assistant",
                    "content": (
                        f"Proposal: {proposal['proposal_url']}\n"
                        f"Image: {proposal['image_url']}\n"
                        f"External reference: {proposal['url']}"
                    ),
                }
            )

        try:
            with patch.object(telegram_agent.requests, "post", fake_post):
                response = self._post_message(
                    f"Show proposal {proposal_id}, its image, and its listed product link",
                    telegram_user_id=telegram_user_id,
                    update_id=_unique_id(),
                )

            self.assertEqual(response.status_code, 200)
            expected_proposal_url = f"https://vote.example/proposal/{proposal_id}"
            expected_image_url = "https://vote.example/static/uploads/telegram%20image.png"
            reply = RecordingTelegramClient.instances[-1].long_messages[0]
            self.assertIn(expected_proposal_url, reply)
            self.assertIn(expected_image_url, reply)
            self.assertIn("https://vendor.example/item", reply)
            self.assertEqual(RecordingTelegramClient.instances[-1].sent_photos, [(expected_image_url, None)])
            tool_payload = json.loads(model_payloads[1]["messages"][-1]["content"])
            self.assertEqual(tool_payload["proposals"][0]["url"], "https://vendor.example/item")
        finally:
            conn = budget_app.get_db()
            conn.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
            if previous_url is None:
                conn.execute("DELETE FROM settings WHERE key = 'url'")
            else:
                conn.execute("UPDATE settings SET value = ? WHERE key = 'url'", (previous_url,))
            conn.commit()
            conn.close()

    def test_queue_full_deletes_thinking_message_and_sends_busy_notice(self):
        telegram_user_id = _unique_id()
        self._link_member(1, telegram_user_id)
        main_routes._telegram_agent_executor = SyncExecutor(reject=True)

        response = self._post_message("What's our budget?", telegram_user_id=telegram_user_id, update_id=_unique_id())

        self.assertEqual(response.status_code, 200)
        client = RecordingTelegramClient.instances[0]
        self.assertIn("🤔 Thinking…", client.sent_messages)
        self.assertEqual(client.deleted_message_ids, [RecordingTelegramClient.next_thinking_message_id])
        self.assertIn("⏳ The assistant is busy right now. Please try again shortly.", client.sent_messages)
        self.assertEqual(client.long_messages, [])

    def test_failed_reply_delivery_is_reported_in_structured_job_log(self):
        telegram_user_id = _unique_id()
        self._link_member(1, telegram_user_id)
        response_payload = FakeModelResponse({"role": "assistant", "content": "Hello"})

        with patch.object(telegram_agent.requests, "post", return_value=response_payload), \
             patch.object(RecordingTelegramClient, "send_long_message", return_value=False), \
             self.assertLogs(main_routes.app.logger, level="INFO") as logs:
            response = self._post_message(
                "Hello", telegram_user_id=telegram_user_id, update_id=_unique_id()
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('"reason_code": "reply_delivery_failed"', "\n".join(logs.output))

    def test_unexpected_reply_error_is_logged_and_user_gets_a_graceful_message(self):
        # A submitted job runs on a background thread via the bounded executor; nothing
        # else ever observes an exception raised there (concurrent.futures silently drops
        # it unless something calls future.result()/.exception()). Simulate a failure mode
        # _natural_language_reply's own except clause doesn't cover (a bare TypeError,
        # unlike the requests.RequestException/RuntimeError/KeyError/IndexError/ValueError
        # it explicitly catches) to prove the outer safety net in _answer_and_send logs it
        # and still delivers a reply and cleans up the thinking message, instead of the
        # update silently vanishing with no reply and no operator signal.
        telegram_user_id = _unique_id()
        self._link_member(1, telegram_user_id)
        main_routes._telegram_agent_executor = SyncExecutor()

        def _raise(*_args, **_kwargs):
            raise TypeError("boom")

        with patch.object(telegram_agent.requests, "post", _raise):
            with self.assertLogs(main_routes.app.logger, level="ERROR") as logs:
                response = self._post_message(
                    "What's our budget?", telegram_user_id=telegram_user_id, update_id=_unique_id()
                )

        self.assertEqual(response.status_code, 200)
        client = RecordingTelegramClient.instances[0]
        self.assertEqual(client.deleted_message_ids, [RecordingTelegramClient.next_thinking_message_id])
        self.assertEqual(len(client.long_messages), 1)
        self.assertIn("Something went wrong", client.long_messages[0])
        self.assertTrue(
            any("Unhandled error generating Telegram assistant reply" in message for message in logs.output)
        )

    def test_duplicate_update_id_is_acknowledged_without_repeating_work(self):
        telegram_user_id = _unique_id()
        update_id = _unique_id()
        self._link_member(1, telegram_user_id)
        response_body = FakeModelResponse({"role": "assistant", "content": "Hi again."})
        with patch.object(telegram_agent.requests, "post", lambda *_a, **_kw: response_body):
            first = self._post_message("Hello", telegram_user_id=telegram_user_id, update_id=update_id)
            second = self._post_message("Hello", telegram_user_id=telegram_user_id, update_id=update_id)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(RecordingTelegramClient.instances), 1)
        self.assertEqual(main_routes._telegram_agent_executor.submitted, 1)

    def test_admin_mutation_confirm_flow_creates_exactly_one_proposal(self):
        telegram_user_id = _unique_id()
        title = f"Webhook-tested widget {telegram_user_id}"
        self._link_member(1, telegram_user_id, is_admin=True)
        propose_response = FakeModelResponse(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-2",
                        "type": "function",
                        "function": {
                            "name": "create_proposal",
                            "arguments": f'{{"title":"{title}","amount":42}}',
                        },
                    }
                ],
            }
        )
        with patch.object(telegram_agent.requests, "post", lambda *_a, **_kw: propose_response):
            propose = self._post_message(
                "Please create a proposal for a widget", telegram_user_id=telegram_user_id, update_id=_unique_id()
            )
        self.assertEqual(propose.status_code, 200)
        propose_client = RecordingTelegramClient.instances[-1]
        self.assertIn("/confirm", propose_client.long_messages[0])

        # /confirm also triggers a *second* TelegramClient: the group-announcement
        # broadcast for the newly created proposal (_notify_created_proposal), created
        # after the reply client. The reply itself is on the first of the two.
        clients_before_confirm = len(RecordingTelegramClient.instances)
        confirm = self._post_message(
            "/confirm", telegram_user_id=telegram_user_id, update_id=_unique_id(), message_id=2
        )
        self.assertEqual(confirm.status_code, 200)
        confirm_client = RecordingTelegramClient.instances[clients_before_confirm]
        self.assertIn("create_proposal completed", confirm_client.long_messages[0])

        conn = budget_app.get_db()
        rows = conn.execute("SELECT id FROM proposals WHERE title = ?", (title,)).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)

    def test_admin_mutation_confirm_rejected_after_admin_role_removed(self):
        telegram_user_id = _unique_id()
        self._link_member(1, telegram_user_id, is_admin=True)
        propose_response = FakeModelResponse(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-3",
                        "type": "function",
                        "function": {
                            "name": "create_proposal",
                            "arguments": '{"title":"Should never be created","amount":42}',
                        },
                    }
                ],
            }
        )
        with patch.object(telegram_agent.requests, "post", lambda *_a, **_kw: propose_response):
            propose = self._post_message(
                "Please create a proposal for a widget", telegram_user_id=telegram_user_id, update_id=_unique_id()
            )
        self.assertEqual(propose.status_code, 200)

        # Role removed between the proposal and the confirmation.
        self._link_member(1, telegram_user_id, is_admin=False)

        confirm = self._post_message(
            "/confirm", telegram_user_id=telegram_user_id, update_id=_unique_id(), message_id=2
        )
        self.assertEqual(confirm.status_code, 200)
        confirm_client = RecordingTelegramClient.instances[-1]
        self.assertIn("Only a linked administrator can confirm", confirm_client.long_messages[0])

        conn = budget_app.get_db()
        rows = conn.execute(
            "SELECT id FROM proposals WHERE title = 'Should never be created'"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 0)

        # Restore admin so later tests relying on member id 1 being an admin are unaffected.
        self._link_member(1, telegram_user_id, is_admin=True)


if __name__ == "__main__":
    unittest.main()
