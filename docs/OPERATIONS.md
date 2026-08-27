# Operations and Diagnostics

This guide is the operator-facing reference for startup health, scheduled work,
backups, MCP failures, OIDC failures, and the Telegram assistant. Deployment and
environment setup remain in [`QUICKSTART.md`](QUICKSTART.md); behavioral contracts
remain in [`SPEC.md`](SPEC.md).

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
| `queue_full` | The bounded worker pool rejected the request before execution. |
| `worker_cancelled` | The executor cancelled an accepted future. |
| `unexpected_worker_failure` | A programming error escaped the typed worker boundary; inspect the attached traceback. |

Prompts, model replies, tool arguments, API keys, and tokens are deliberately absent
from these job records. `tool_name` is logged, but tool arguments are not.

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

```bash
# Complete automated regression suite
pytest -q tests/

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
