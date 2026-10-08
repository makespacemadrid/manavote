# Operations and Diagnostics

This guide is the operator-facing reference for startup health, scheduled work,
backups, MCP failures, OIDC failures, and the Telegram assistant. Deployment and
environment setup remain in [`QUICKSTART.md`](QUICKSTART.md); behavioral contracts
remain in [`SPEC.md`](SPEC.md).

## Contents

- [Startup health](#startup-health)
- [Backup lifecycle](#backup-lifecycle)
- [Telegram assistant jobs](#telegram-assistant-jobs)
- [Telegram assistant mutations](#telegram-assistant-mutations)
- [Votes blocked by policy](#votes-blocked-by-policy)
- [Koin ledger corrections](#koin-ledger-corrections)
- [Forum-topic and mention routing](#forum-topic-and-mention-routing-decisions)
- [MCP and OIDC failures](#mcp-and-oidc-failures)
- [Useful diagnostic checks](#useful-checks)

## Startup health

Every boot emits a `startup_summary` record with:

- `mode`: resolved Flask environment;
- `status`: `ready` or `degraded`;
- `degraded_reasons`: stable codes for optional startup work that failed.

Database initialization is mandatory and fails startup. Scheduler, automatic-backup,
and Telegram webhook synchronization problems are reported as degraded startup rather
than hiding the application behind a generic failure.

Common startup diagnostics:

| Reason code | Meaning | Operator action |
| --- | --- | --- |
| `telegram_webhook_missing_base_url` | Telegram is configured but the public base URL is unavailable. | Set the Base URL in Admin → Telegram Configuration, then restart. |
| `telegram_webhook_failed` | Telegram rejected or could not receive webhook synchronization. | Verify the bot token, webhook secret, outbound HTTPS, and public URL. |
| `scheduler_start_failed` | The backup scheduler could not start. | Inspect the adjacent exception, confirm APScheduler is installed, and ensure only the intended process owns scheduling. |
| `auto_backup_check_failed` | The startup backup check failed unexpectedly. | Check backup-directory permissions and available disk space. |
| `missing_bot_username_for_group` | A Telegram group/supergroup or forum thread is configured without an exact bot username. | Set `TELEGRAM_BOT_USERNAME` without the leading `@`; private-chat-only configurations do not trigger this warning. |

The bot-username warning is advisory and does not mark startup degraded. It identifies
an unsafe group-routing default where mentions or commands aimed at another bot could
otherwise be treated as addressed to ManaVote.

## Backup lifecycle

Admin, scheduled, and startup backups use the same structured audit shape. Event names
identify the source:

- `admin_backup_created` / `admin_backup_failed`;
- `scheduled_backup_created` / `scheduled_backup_failed`;
- `startup_backup_created` / `startup_backup_failed`.

Successful records include `backup_type`, `file_name`, and `pruned_count`. Failures
include `backup_type`, `error`, and one of these stable reason codes:

| Reason code | Failure class |
| --- | --- |
| `backup_io_error` | Filesystem access, missing input, permissions, or disk I/O. |
| `backup_archive_error` | Upload archive creation/copy failure reported by `shutil`. |
| `backup_configuration_error` | Invalid backup configuration or retention input. |

Unexpected programming errors are not relabeled as routine backup failures; they are
allowed to surface with their traceback.

## Telegram assistant jobs

Configured natural-language requests emit `telegram_assistant_job` records. Correlate
all records for one request with `update_id`, `chat_id`, and `actor_member_id`.

Typical event sequence:

1. `started` with `reason_code=worker_started` and `queue_wait_ms`;
2. one or more `model_request_completed` records with `model_round` and
   `model_latency_ms`;
3. zero or more `tool_call_received` records with `tool_name`;
4. `completed` with `job_duration_ms` and the final outcome.

Completion/rejection reason codes:

| Reason code | Meaning |
| --- | --- |
| `completed` | Reply generation, delivery, and thinking-message cleanup completed. |
| `reply_generation_failed` | The model, MCP round, history store, or expected adapter boundary failed; a fallback reply was attempted. |
| `reply_delivery_failed` | Telegram reply delivery raised an expected client/input error. |
| `thinking_cleanup_failed` | The temporary thinking message could not be deleted. |
| `member_capacity_exceeded` | This linked member reached `TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER` outstanding jobs in this process. No thinking message or model/MCP call was made; wait for an existing reply and retry. |
| `queue_full` | The bounded worker pool rejected the request before execution; its member reservation was released and thinking-message cleanup attempted. |
| `submission_failed` | Executor submission raised; member/global admission is released and thinking-message cleanup attempted. |
| `thinking_creation_failed` | Creating the temporary Telegram message raised; the member reservation was released. |
| `worker_cancelled` | The executor cancelled an accepted future. |
| `unexpected_worker_failure` | An error escaped the typed worker boundary; correlate safe update/actor metadata. Assistant logs omit exception bodies and tracebacks. |
| `input_budget_exceeded` | Current input exceeds its UTF-8-byte budget; send a shorter question. |
| `context_budget_exceeded` | Required instructions, schemas, current turn, and tool results cannot fit; request fewer results or reset history. Earlier actions may already have completed. |
| `credential_input_rejected` | A configured credential or conventionally sensitive field was detected before input/tool arguments reached the next boundary. |

Prompts, model replies, tool arguments, API keys, and tokens are deliberately absent
from these job records. `tool_name` is logged, but tool arguments are not.

`TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER` is a positive integer, default `1`, loaded at
process startup. It counts queued and running assistant jobs by linked member ID across
chats. Invalid values prevent startup. Admission is acquired before the thinking message;
completion, failure, rejected/failed submission, and queued cancellation release it once.
Cancelled queued jobs also attempt to remove their thinking message.

Accounting and the global executor are process-local. With `W` WSGI processes, a member
can have up to `W × limit` outstanding jobs across those processes; each process retains
four model workers and 32 pending slots. Tune cautiously and restart to apply. This is
outstanding-work admission, without rate-per-minute throttling or distributed fairness.

`/confirm` uses admission; capacity rejection leaves its pending mutation untouched.
`/cancel` is now a deterministic control path before admission: it cancels the sender's
queued jobs in this process/current conversation and atomically clears their owned
pending action. It does not call the model or create a thinking message. Starting/running
work is reported without interruption or rollback. A request in another WSGI process
cannot be cancelled here; an unsuccessful lookup does not claim that no work exists.
`/help`, linking, deterministic votes, and `/reset` retain their dispatch. Workers refresh
linked identity and role before executing queued work, in addition to existing confirmation checks.

## Assistant operator health

Visit `GET /admin/assistant-health` in an authenticated administrator session. It uses
the existing web administrator gate (not the REST admin key), returns JSON, and sends
`Cache-Control: no-store`. Regular members and anonymous callers receive redirects.

| Field | Meaning / operator action |
|---|---|
| `scope`, `reset` | `process`, `process_restart`; each worker has independent counters and registry. Polls may hit different workers. These values are not fleet totals. |
| `status` | `disabled` (missing model/MCP configuration), `misconfigured` (invalid timeout), `saturated` (worker/queue capacity occupied), or `ready` (configuration/capacity available). This does not probe provider connectivity. |
| `queued`, `active` | Current owned jobs, including short pre-submission setup in queued. Sustained saturation calls for inspecting queue/model latency before increasing capacity. |
| `terminal` | Exactly-once completed/failed/cancelled/rejected job counts; early admission refusal also increments rejected. `/confirm` is an assistant job; `/cancel` is a control request. |
| `reasons` | Stable completion/rejection reason counts, including member capacity, queue/submission/thinking failures and budget/credential rejections. No actor/chat/tool-argument labels. |
| `stage_failures` | Model, MCP, and reply-delivery failure counts. Inspect the matching stage and safe job events; a handled tool error still records a failed tool stage/job even when a useful reply is delivered. |
| `latency_ms` | Bounded count/mean/max summaries for queue, model, MCP, and delivery. High queue wait suggests saturation; high model/MCP latency suggests inspecting the provider/tool. No per-request samples persist here. |
| `configuration` | Safe model identifier, timeout, worker/queue/member capacities, and input/context/output budgets. Provider URL and credentials are omitted. Restart processes to reset counters/apply startup limits. |

Cancellation is owned by linked member plus chat/Telegram user, matching conversation
history (including that user's threads in one chat). Relinking cannot cancel the prior
member's job/action. Legacy pending actions with no recorded member cannot be claimed by
the new control path; let them expire or use the existing explicit reset. Start/cancel
races report only confirmed queued cancellation; work already starting/running may reply.
Cancelled jobs release both capacities once, remove registry entries, and attempt status
cleanup even when Telegram rejects deletion. There is no cross-worker queue or running
HTTP interruption. Aggregate health contains no prompts, replies, tool arguments/results,
credentials, provider URLs, or member/chat identities.

## Assistant model safeguards

Every model round counts serialized UTF-8 bytes plus 256 framing units and 64 units
per message, including system/current input, tools, history, and tool results. The
output reserve is included and sent as `max_tokens`. Set the context budget no higher
than the provider's verified context limit; this estimate is conservative for byte-based
tokenizers, not model discovery or a guarantee for custom tokenizers. The provider must
accept `max_tokens`. Initial member/admin tool schemas measured 4,813/9,223 units with
framing; defaults leave room for the built-in prompt and a 4,096-byte question.

Old history is dropped in complete user-led groups; incomplete tool-call/result groups
are excluded. Required current tool exchanges and actor instructions are never truncated.
Budget rejection sends localized feedback and releases admission. It does not retry or
undo previously committed tool actions.

The assistant redacts configured credentials, conventional sensitive JSON fields,
credential assignments, bearer values, and URL credentials from model payloads, new
history writes, confirmation displays, tool errors, and replies. Input or allowed tool
arguments containing these values are rejected before persistence/execution. Required
authentication headers still carry credentials to their destination. Arbitrary unlabelled
secrets in free text cannot reliably be recognized. Existing stored history is scrubbed
on read, not rewritten/deleted; retention remains separate. Failure logs retain stable
reason codes and exception types rather than bodies/tracebacks. Avoid request/body debug
logging at these boundaries.

## Telegram assistant mutations

`/confirm`-reachable mutations (`create_proposal`, `create_poll`,
`update_voting_settings`) emit a separate `telegram_assistant_mutation` record for each
step of the propose/confirm lifecycle — a dedicated audit trail, distinct from the
general-purpose `telegram_assistant_job` records above, findable the same way backup and
Telegram-link events already are. Correlate records for one action with `tool_name`,
`actor_member_id`, and `arguments_digest` (a stable hash of the tool arguments, not the
arguments themselves — arguments are never logged).

Typical event sequence: `proposed` → `confirmed` → `completed` (or `failed`), or
`proposed` → one of `cancelled`/`expired`/`rejected` if confirmation never completes.

| Event | Reason code | Meaning |
| --- | --- | --- |
| `proposed` | `ok` | A mutating tool call was intercepted and stored pending `/confirm`. |
| `confirmed` | `ok` | Confirmation passed every revalidation check; the MCP call is about to run. |
| `completed` | `ok` | The confirmed MCP call succeeded. |
| `failed` | `mcp_error` | The confirmed MCP call returned an error. |
| `cancelled` | `user_cancelled` | The member issued `/cancel`. |
| `cancelled` | `reset_command` | `/reset` discarded a pending action along with conversation history. |
| `expired` | `confirmation_ttl_exceeded` | `/confirm` arrived after `TELEGRAM_CONFIRM_TTL_SECONDS`. |
| `rejected` | `not_admin` | The confirming user is not a linked administrator. |
| `rejected` | `actor_changed` | The linked member changed between propose and confirm. |
| `rejected` | `arguments_tampered` | The stored arguments no longer match the digest captured at propose time. |
| `rejected` | `schema_changed` | The tool's input schema (or the tool itself) changed since propose time — e.g. a process restart with an updated MCP tool registry. |

The `arguments_tampered` and `schema_changed` checks exist so a confirmed mutation is
provably the one that was proposed: a stale or corrupted pending row is rejected at
confirm time instead of executing against a contract that no longer matches what the
member saw.

## Votes blocked by policy

A vote rejected by `proposal_vote_mode`, `poll_vote_mode`, or
`telegram_require_linked_vote` logs a plain-text `event=... source=... mode=...` record
(the same shape `record_proposal_vote`'s own accept/reject logging already used), so a
policy-blocked vote is distinguishable from an ordinary invalid-vote rejection without
reading logs line-by-line.

| Log line prefix | Meaning |
| --- | --- |
| `event=proposal_vote_rejected ... reason_code=channel_disabled` | A proposal vote was blocked by `proposal_vote_mode` (web or Telegram). |
| `event=proposal_vote_rejected ... reason_code=link_required` | A Telegram proposal vote was blocked because `telegram_require_linked_vote` is enabled and the sender isn't linked. |
| `event=poll_vote_rejected ... reason_code=channel_disabled` | A poll vote was blocked by `poll_vote_mode` (web or Telegram). |
| `event=poll_vote_rejected ... reason_code=link_required` | A Telegram poll vote was blocked because `telegram_require_linked_vote` is enabled and the sender isn't linked. |

`source=web` or `source=telegram` identifies the channel; `mode` is the effective vote
mode at rejection time. `poll_id`/`proposal_id` and `member_id` are `None` when the
channel-disabled check fires before either is resolved (the check runs before any
poll/member lookup on some paths) — the record is still useful in aggregate ("N vote
attempts blocked by policy") even without full identity.

## Koin ledger corrections

An administrator editing an existing koin movement emits two informational records:

| Log prefix | Meaning |
| --- | --- |
| `coin_movement_updated` | The koin service validated and committed the correction. The record includes the movement, item, member, kind, and submitted quantity. |
| `coin_movement_updated_by_admin` | The protected web route completed the correction. `movement_id` identifies the corrected row and `member_id` identifies the administrator who submitted it. |

The corrected database row retains its original `id`, `idempotency_key`, and
`created_at`, and changes `source` to `admin`. Use those preserved identifiers plus the
two log records when investigating a correction. The current log records confirm the
new values and acting administrator; they do not retain a copy of the row's previous
values.

## Forum-topic and mention routing decisions

Group/supergroup messages that aren't a deterministic command (`/link`, `/vote`, etc.)
log a `telegram_routing_decision` record explaining why the assistant did or didn't pick
the message up — the "why did the bot stay silent (or respond) here" case. Private chats
are always trivially `private` and not logged; only group-chat addressing is ambiguous
enough to be worth a record.

| Reason code | Meaning |
| --- | --- |
| `reply_to_bot` | The message replies to the bot's own message. |
| `mentioned` | The message contains an `@mention` (or, under Telegram privacy mode, an unidentified mention entity) matching the bot. |
| `forum_topic` | The message is in the configured assistant forum topic (`TELEGRAM_CHAT_ID`/`TELEGRAM_THREAD_ID`), which overrides an otherwise-unaddressed message. |
| `unaddressed` | None of the above; the assistant ignored the message. |

`addressed=True/False` mirrors whether the message was actually routed to the assistant.
`chat_id`/`chat_type` identify where the decision was made.

## MCP and OIDC failures

MCP transport/application failures log
`mcp_request_failure reason_code=application_failure` with the request ID or TCP
transport marker. Clients receive JSON-RPC code `-32000` and the generic message
`Internal server error`; internal exception text is only written server-side.

OIDC token exchange and validation failures log
`oidc_callback_failure reason_code=oidc_token_exchange_failed` plus the exception type.
Members are redirected to the login page with a safe retry message; tokens and provider
response bodies are not logged by this handler.

## Useful checks

These checks are for production diagnosis and operational boundaries. For the complete
suite and feature-focused regression packs, see [`TESTING.md`](TESTING.md).

```bash
# Startup, backup, identity, MCP, and Telegram operational boundaries
pytest -q \
  tests/test_app_startup.py \
  tests/test_backup_service.py \
  tests/test_oidc_auth.py \
  tests/test_mcp_server.py \
  tests/test_telegram_natural_language_webhook.py

# The application exception audit should return no matches
rg -n "except Exception" app
```

When debugging, search by stable reason code first, then narrow by request/update/member
identifier. Do not paste production tokens, Telegram payloads, OIDC responses, or raw
database contents into issue reports.
