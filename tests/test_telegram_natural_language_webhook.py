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
from app.integrations.member_admission import MemberAdmission
from app.integrations.assistant_jobs import AssistantJobs
from concurrent.futures import Future, ThreadPoolExecutor
import threading
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


class HoldingExecutor:
    """Keep accepted work queued until the test completes or cancels it."""
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args, **kwargs):
        future = Future()
        self.jobs.append((future, function, args, kwargs))
        return future

    def run_next(self):
        future, function, args, kwargs = self.jobs.pop(0)
        if future.set_running_or_notify_cancel():
            try:
                future.set_result(function(*args, **kwargs))
            except BaseException as exc:
                future.set_exception(exc)
        return future


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
        self._old_admission = main_routes._telegram_member_admission
        self._old_jobs = main_routes._telegram_jobs
        main_routes._telegram_jobs = AssistantJobs()
        main_routes._telegram_member_admission = MemberAdmission()
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
        main_routes._telegram_member_admission = self._old_admission
        main_routes._telegram_jobs = self._old_jobs
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

    def _post_message(self, text, telegram_user_id, update_id, message_id=1, chat_id=None, language_code="en"):
        return self.client.post(
            "/telegram/webhook/nl-hook-secret",
            json={
                "update_id": update_id,
                "message": {
                    "message_id": message_id,
                    "text": text,
                    "from": {"id": telegram_user_id, "username": f"user{telegram_user_id}", "language_code": language_code},
                    "chat": {"id": chat_id if chat_id is not None else telegram_user_id, "type": "private"},
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

    def test_linked_group_sender_can_address_bot_by_replying_to_its_message(self):
        telegram_user_id = _unique_id()
        self._link_member(1, telegram_user_id)
        main_routes.TELEGRAM_BOT_USERNAME = "manavote_bot"
        model_response = FakeModelResponse(
            {"role": "assistant", "content": "Because I checked the current records."}
        )

        with patch.object(telegram_agent.requests, "post", return_value=model_response):
            response = self.client.post(
                "/telegram/webhook/nl-hook-secret",
                json={
                    "update_id": _unique_id(),
                    "message": {
                        "message_id": 73,
                        "text": "How do you know that?",
                        "from": {"id": telegram_user_id},
                        "chat": {"id": -100123, "type": "supergroup"},
                        "reply_to_message": {
                            "message_id": 72,
                            "from": {
                                "id": 999,
                                "is_bot": True,
                                "username": "manavote_bot",
                            },
                        },
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(main_routes._telegram_agent_executor.submitted, 1)
        client = RecordingTelegramClient.instances[0]
        self.assertEqual(client.chat_id, "-100123")
        self.assertEqual(client.reply_to_message_id, 73)
        self.assertIn("Because I checked", client.long_messages[0])

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


    def test_member_busy_across_chats_is_localized_without_thinking_or_model(self):
        user_id = _unique_id()
        self._link_member(1, user_id)
        executor = HoldingExecutor()
        main_routes._telegram_agent_executor = executor
        with patch.object(telegram_agent, "answer") as answer, self.assertLogs(main_routes.app.logger, level="INFO") as logs:
            self._post_message("first", user_id, _unique_id(), chat_id=101)
            rejected = self._post_message("sensitive prompt", user_id, _unique_id(), chat_id=202, language_code="es-ES")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(len(executor.jobs), 1)
        answer.assert_not_called()
        busy = RecordingTelegramClient.instances[-1]
        self.assertEqual(len(busy.sent_messages), 1)
        self.assertIn("Ya tienes", busy.sent_messages[0])
        self.assertEqual(busy.deleted_message_ids, [])
        self.assertEqual(busy.long_messages, [])
        self.assertIn('"reason_code": "member_capacity_exceeded"', "\n".join(logs.output))
        self.assertNotIn("sensitive prompt", "\n".join(logs.output))
        executor.jobs[0][0].cancel()

    def test_another_member_is_admitted_and_duplicate_does_not_take_capacity(self):
        first_id, other_id = _unique_id(), _unique_id()
        self._link_member(1, first_id)
        conn = budget_app.get_db()
        other = conn.execute("INSERT INTO members (username, password_hash, telegram_user_id) VALUES (?, 'unused', ?)", (f"admission-{other_id}", other_id)).lastrowid
        conn.commit()
        conn.close()
        executor = HoldingExecutor()
        main_routes._telegram_agent_executor = executor
        update_id = _unique_id()
        self._post_message("first", first_id, update_id)
        self._post_message("first", first_id, update_id)
        self.assertEqual(len(RecordingTelegramClient.instances), 1)
        self._post_message("other", other_id, _unique_id())
        self.assertEqual(len(executor.jobs), 2)
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {1: 1, other: 1})
        for future, *_ in executor.jobs:
            future.cancel()
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})

    def test_concurrent_webhooks_admit_only_one_request_for_linked_member(self):
        from app.integrations.telegram_webhook import TelegramUpdateDeduplicator
        from app.services.telegram_access_service import TelegramPrincipal
        from app.web.routes import telegram_routes
        main_routes._telegram_agent_executor = executor = HoldingExecutor()
        barrier = threading.Barrier(8)
        def post(index):
            barrier.wait(timeout=5)
            return budget_app.app.test_client().post('/telegram/webhook/nl-hook-secret', json={
                'update_id': _unique_id(), 'message': {'text': 'hello', 'from': {'id': 100},
                    'chat': {'id': index + 1, 'type': 'private'}}}).status_code
        with patch.object(telegram_routes, 'get_telegram_principal', return_value=TelegramPrincipal(1, 100, True)), \
             patch.object(main_routes, '_telegram_update_deduplicator', TelegramUpdateDeduplicator()), \
             ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(post, range(8)))
        self.assertEqual(statuses, [200] * 8)
        self.assertEqual(len(executor.jobs), 1)
        self.assertEqual(sum('🤔 Thinking…' in c.sent_messages for c in RecordingTelegramClient.instances), 1)
        executor.jobs[0][0].cancel()

    def test_queued_cancel_cleans_thinking_and_allows_next_request(self):
        user_id = _unique_id()
        self._link_member(1, user_id)
        main_routes._telegram_agent_executor = executor = HoldingExecutor()
        self._post_message("first", user_id, _unique_id())
        original = RecordingTelegramClient.instances[-1]
        self.assertTrue(executor.jobs[0][0].cancel())
        self.assertEqual(original.deleted_message_ids, [RecordingTelegramClient.next_thinking_message_id])
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})
        self._post_message("retry", user_id, _unique_id())
        self.assertEqual(len(executor.jobs), 2)
        executor.jobs[1][0].cancel()

    def test_submission_failure_releases_admission_and_cleans_thinking(self):
        user_id = _unique_id()
        self._link_member(1, user_id)
        with patch.object(main_routes._telegram_agent_executor, 'submit', side_effect=RuntimeError('shutdown')):
            with self.assertRaisesRegex(RuntimeError, 'shutdown'):
                self._post_message('first', user_id, _unique_id())
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})
        self.assertEqual(RecordingTelegramClient.instances[-1].deleted_message_ids, [RecordingTelegramClient.next_thinking_message_id])
        with patch.object(telegram_agent, 'answer', return_value='retry worked'):
            self.assertEqual(self._post_message('retry', user_id, _unique_id()).status_code, 200)
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})

    def test_thinking_creation_failure_does_not_leak_admission(self):
        user_id = _unique_id()
        self._link_member(1, user_id)
        with patch.object(RecordingTelegramClient, 'send_message_with_id', side_effect=ValueError('delivery failed')):
            with self.assertRaisesRegex(ValueError, 'delivery failed'):
                self._post_message('first', user_id, _unique_id())
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})

    def test_model_and_delivery_failures_each_release_admission(self):
        user_id = _unique_id()
        self._link_member(1, user_id)
        with patch.object(telegram_agent, 'answer', side_effect=RuntimeError('model failed')):
            self.assertEqual(self._post_message('first', user_id, _unique_id()).status_code, 200)
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})
        with patch.object(telegram_agent, 'answer', return_value='reply'), \
             patch.object(RecordingTelegramClient, 'send_long_message', side_effect=ValueError('delivery failed')):
            self.assertEqual(self._post_message('second', user_id, _unique_id()).status_code, 200)
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})

    def test_busy_confirmation_preserves_pending_but_cancel_clears_owned_job_and_action(self):
        user_id = _unique_id()
        self._link_member(1, user_id, is_admin=True)
        key = telegram_agent._conversation_key(user_id, user_id)
        action = telegram_agent.PendingAction(tool_name='create_proposal', arguments={'title': 'Item', 'amount': 10},
            created_at=time.time(), actor_member_id=1)
        telegram_agent._put_pending(key, action)
        main_routes._telegram_agent_executor = executor = HoldingExecutor()
        self._post_message('first', user_id, _unique_id())
        self._post_message('/confirm', user_id, _unique_id())
        self.assertIs(telegram_agent._get_pending(key), action)
        with patch.object(telegram_agent.requests, 'post') as model:
            self._post_message('/cancel', user_id, _unique_id())
        model.assert_not_called()
        self.assertIsNone(telegram_agent._get_pending(key))
        self.assertEqual(len(executor.jobs), 1)
        self.assertTrue(executor.jobs[0][0].cancelled())
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})
        self.assertIn('Pending action cancelled', RecordingTelegramClient.instances[-1].sent_messages[0])
        self.assertEqual(main_routes._telegram_jobs.snapshot()['terminal']['cancelled'], 1)
        main_routes._telegram_agent_executor = SyncExecutor()
        with patch.object(telegram_agent.requests, 'post') as model:
            self._post_message('/cancel', user_id, _unique_id())
        model.assert_not_called()
        self.assertIsNone(telegram_agent._get_pending(key))
        self.assertIn('No queued request', RecordingTelegramClient.instances[-1].sent_messages[0])

    def test_global_queue_rejection_releases_member_slot_and_localizes_reply(self):
        user_id = _unique_id()
        self._link_member(1, user_id)
        main_routes._telegram_agent_executor = SyncExecutor(reject=True)
        self._post_message('first', user_id, _unique_id(), language_code='es')
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})
        self.assertIn('ocupado', RecordingTelegramClient.instances[-1].sent_messages[-1])
        main_routes._telegram_agent_executor = SyncExecutor()
        with patch.object(telegram_agent, 'answer', return_value='reply'):
            self.assertEqual(self._post_message('retry', user_id, _unique_id()).status_code, 200)
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})


    def test_input_rejection_is_localized_and_releases_job_capacity(self):
        user_id = _unique_id()
        self._link_member(1, user_id)
        with patch.object(telegram_agent.requests, "post") as model:
            response = self._post_message("a" * 4097, user_id, _unique_id(), language_code="es")
        self.assertEqual(response.status_code, 200)
        model.assert_not_called()
        self.assertIn("más corta", RecordingTelegramClient.instances[-1].long_messages[0])
        self.assertEqual(RecordingTelegramClient.instances[-1].deleted_message_ids, [555])
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})

    def test_failure_payload_credentials_do_not_reach_logs_or_replies(self):
        import requests
        user_id = _unique_id()
        self._link_member(1, user_id)
        with patch.object(telegram_agent.requests, "post", side_effect=requests.HTTPError("password=private-provider-secret")), \
             self.assertLogs(main_routes.app.logger, level="INFO") as records:
            self._post_message("hello", user_id, _unique_id())
        self.assertNotIn("private-provider-secret", "\n".join(records.output))
        self.assertNotIn("private-provider-secret", "\n".join(RecordingTelegramClient.instances[-1].long_messages))
        self.assertEqual(main_routes._telegram_member_admission._outstanding, {})


    def test_cancelled_queued_job_never_runs_and_retry_control_is_idempotent(self):
        user_id=_unique_id()
        self._link_member(1,user_id)
        main_routes._telegram_agent_executor=executor=HoldingExecutor()
        self._post_message('queued',user_id,_unique_id())
        queued_client=RecordingTelegramClient.instances[-1]
        cancel_update=_unique_id()
        with patch.object(telegram_agent,'answer') as answer:
            self._post_message('/cancel',user_id,cancel_update,language_code='es')
            self._post_message('/cancel',user_id,cancel_update,language_code='es')
            executor.run_next()
        answer.assert_not_called()
        self.assertEqual(queued_client.long_messages,[])
        self.assertEqual(queued_client.deleted_message_ids,[555])
        self.assertIn('cancelada',RecordingTelegramClient.instances[-1].sent_messages[0])
        snapshot=main_routes._telegram_jobs.snapshot()
        self.assertEqual((snapshot['queued'],snapshot['active']),(0,0))
        self.assertEqual(snapshot['terminal']['cancelled'],1)
        self.assertEqual(main_routes._telegram_member_admission._outstanding,{})

    def test_other_member_in_shared_chat_cannot_cancel_owned_job(self):
        owner,other=_unique_id(),_unique_id()
        conn=budget_app.get_db()
        conn.execute("INSERT OR IGNORE INTO members(id,username,password_hash) VALUES (2,'cancel-test-member','unused')")
        conn.commit();conn.close()
        self._link_member(1,owner)
        self._link_member(2,other)
        main_routes._telegram_agent_executor=executor=HoldingExecutor()
        self._post_message('queued',owner,_unique_id(),chat_id=900)
        self._post_message('/cancel',other,_unique_id(),chat_id=900)
        self.assertFalse(executor.jobs[0][0].cancelled())
        self.assertIn('No queued request',RecordingTelegramClient.instances[-1].sent_messages[0])
        self._post_message('/cancel',owner,_unique_id(),chat_id=900)
        self.assertTrue(executor.jobs[0][0].cancelled())

    def test_relink_cannot_cancel_old_job_or_pending_action_and_worker_revalidates(self):
        user_id=_unique_id()
        self._link_member(1,user_id,is_admin=True)
        key=telegram_agent._conversation_key(user_id,user_id)
        action=telegram_agent.PendingAction('create_poll',{'question':'Safe','options':['A','B']},actor_member_id=1)
        telegram_agent._put_pending(key,action)
        main_routes._telegram_agent_executor=executor=HoldingExecutor()
        self._post_message('queued',user_id,_unique_id())
        original=RecordingTelegramClient.instances[-1]
        conn=budget_app.get_db()
        conn.execute('UPDATE members SET telegram_user_id=NULL WHERE id=1')
        conn.execute("INSERT OR IGNORE INTO members(id,username,password_hash) VALUES (2,'cancel-test-member','unused')")
        conn.execute('UPDATE members SET telegram_user_id=? WHERE id=2',(user_id,))
        conn.commit();conn.close()
        self._post_message('/cancel',user_id,_unique_id())
        self.assertFalse(executor.jobs[0][0].cancelled())
        self.assertIs(telegram_agent._get_pending(key),action)
        with patch.object(telegram_agent,'answer') as answer:
            executor.run_next()
        answer.assert_not_called()
        self.assertIn('linked account changed',original.long_messages[0])
        self.assertEqual(main_routes._telegram_member_admission._outstanding,{})

    def test_running_job_cancel_reports_status_and_preserves_execution(self):
        user_id=_unique_id()
        self._link_member(1,user_id)
        executor=ThreadPoolExecutor(max_workers=1)
        main_routes._telegram_agent_executor=executor
        entered=threading.Event();release=threading.Event()
        def answer(*args,**kwargs):
            entered.set();release.wait(5);return 'completed reply'
        try:
            with patch.object(telegram_agent,'answer',side_effect=answer):
                self._post_message('start',user_id,_unique_id())
                self.assertTrue(entered.wait(5))
                self._post_message('/cancel',user_id,_unique_id())
                self.assertIn('already running',RecordingTelegramClient.instances[-1].sent_messages[0])
                self.assertEqual(main_routes._telegram_jobs.snapshot()['active'],1)
                release.set()
                executor.shutdown(wait=True)
            self.assertEqual(main_routes._telegram_jobs.snapshot()['terminal']['completed'],1)
            self.assertEqual(main_routes._telegram_member_admission._outstanding,{})
        finally:
            release.set();executor.shutdown(wait=True)

    def test_model_tool_and_delivery_failure_stages_are_aggregate_diagnostics(self):
        import requests
        user_id=_unique_id()
        self._link_member(1,user_id)
        with patch.object(telegram_agent.requests,'post',side_effect=requests.HTTPError('private provider error')):
            self._post_message('model failure',user_id,_unique_id())
        tool=FakeModelResponse({'role':'assistant','tool_calls':[{'id':'t','function':{'name':'current_budget','arguments':'{}'}}]})
        reply=FakeModelResponse({'role':'assistant','content':'tool failed'})
        with patch.object(telegram_agent.requests,'post',side_effect=[tool,reply]), \
             patch.object(telegram_agent,'_call_mcp',return_value='{"error":"tool unavailable"}'):
            self._post_message('tool failure',user_id,_unique_id())
        with patch.object(telegram_agent,'answer',return_value='reply'), \
             patch.object(RecordingTelegramClient,'send_long_message',return_value=False):
            self._post_message('delivery failure',user_id,_unique_id())
        snapshot=main_routes._telegram_jobs.snapshot()
        self.assertEqual(snapshot['stage_failures'],{'model':1,'mcp':1,'delivery':1})
        self.assertEqual(snapshot['terminal']['failed'],3)
        self.assertEqual(snapshot['terminal']['completed'],0)
        self.assertEqual(snapshot['latency_ms']['model']['count'],3)
        self.assertEqual(snapshot['latency_ms']['mcp']['count'],1)
        self.assertEqual((snapshot['active'],snapshot['queued']),(0,0))
        self.assertNotIn('private provider error',json.dumps(snapshot))

    def test_cancel_cleanup_failure_does_not_leak_capacity_or_registry(self):
        import requests
        user_id=_unique_id()
        self._link_member(1,user_id)
        main_routes._telegram_agent_executor=executor=HoldingExecutor()
        self._post_message('queued',user_id,_unique_id())
        with patch.object(RecordingTelegramClient,'delete_message',side_effect=requests.RequestException('password=private-cleanup')), \
             self.assertLogs(main_routes.app.logger,level='INFO') as records:
            self._post_message('/cancel',user_id,_unique_id())
        self.assertTrue(executor.jobs[0][0].cancelled())
        self.assertEqual(main_routes._telegram_member_admission._outstanding,{})
        self.assertEqual(main_routes._telegram_jobs.snapshot()['queued'],0)
        self.assertNotIn('private-cleanup','\n'.join(records.output))

    def test_role_removal_while_confirmation_waits_is_revalidated_at_execution(self):
        user_id=_unique_id()
        self._link_member(1,user_id,is_admin=True)
        key=telegram_agent._conversation_key(user_id,user_id)
        telegram_agent._put_pending(key,telegram_agent.PendingAction('create_poll',{'question':'Safe','options':['A','B']},actor_member_id=1))
        main_routes._telegram_agent_executor=executor=HoldingExecutor()
        self._post_message('/confirm',user_id,_unique_id())
        self._link_member(1,user_id,is_admin=False)
        with patch.object(telegram_agent,'_call_mcp') as tool:
            executor.run_next()
        tool.assert_not_called()
        self.assertIn('Only a linked administrator',RecordingTelegramClient.instances[-1].long_messages[0])


if __name__ == "__main__":
    unittest.main()
