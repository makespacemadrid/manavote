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
