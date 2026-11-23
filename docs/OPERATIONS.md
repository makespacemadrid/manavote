# Operations and Diagnostics

## Health Checks

### `/healthz` endpoint

The Flask app exposes a simple health check at `http://localhost:45000/healthz`. This endpoint
returns `200 OK` when the application is healthy and can be used by load balancers and
container orchestration platforms.

**Health check result:** `{"status": "healthy"}`

### Degraded mode

The application can enter a degraded state if:
- Mandatory environment variables are missing
- Database connection fails
- Mandatory startup policy validation fails

Degraded mode does not shut down the application, but some features may be disabled.
The startup summary reports `degraded_reasons` and `mode: "degraded"`.

### Startup summary

At startup, the application reports:
```json
{
  "mode": "production" | "test",
  "degraded_reasons": [...],
  "status": "ready"
}
```

## Backup

### Manual backup

Backups are created from the Admin panel → Settings tab → Backup section:

- Click "Backup Now" to back up the database
- Click "Backup Images Now" to back up uploaded images

Old backups (older than 7 days) are automatically pruned by the daily scheduled job.

### Scheduled backups

Daily backups are run by the APScheduler when `MCP_SERVER_ENABLED` is true. Backups
include:

- **Database backup**: `app_YYYYMMDD.db`
- **Image backup**: `uploads_YYYYMMDD.zip`

Backups are stored in the `backups/` directory and retained according to policy.

### Backup state events

Structured audit events are emitted for all backup operations:

- `db`: `backup_type=db`, `file_name=app_20261118_155618.db`, `status=ok`
- `images`: `backup_type=images`, `file_name=uploads_20261118_155618.zip`, `status=ok`

These events are emitted to the Telegram assistant and recorded in the structured
audit log (viewable in the Admin panel).

### Backup retention

- Database backups are retained indefinitely (or per policy).
- Image backups are retained per configured policy.

### Backup from the Admin panel

1. Navigate to Admin → Settings tab → Backup section
2. Click "Create backup" for DB or Images
3. Download the generated file from the provided link
4. Verify the backup by checking the audit events

### Restoring from backup

1. Navigate to Admin → Settings tab → Backup section
2. Click "Restore" next to the desired backup
3. Follow the on-screen instructions
4. Verify the application is functioning correctly after restoration

## Logs

### Structured logging

The application uses structured JSON logging. Each log entry includes:

- `timestamp` — ISO 8601 format
- `level` — `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `logger` — the Python logger name
- `event` — a descriptive event name
- `structured_fields` — key-value pairs for auditability

### Log locations

- **Container stdout/stderr**: Captured by Docker
- **Application log file**: `app.log` (if configured)
- **Telegram assistant**: Structured events for backup and audit events

### Log levels

- `INFO` — Normal operational events
- `WARNING` — Non-critical issues
- `ERROR` — Critical issues needing attention
- `CRITICAL` — System failures

### Log correlation

Structured events include a `event_id` for correlation across services and time.

## Auditing

### Audit events

Structured audit events are emitted for significant operational actions. Each event includes:

- `event_id` — unique identifier
- `event_type` — category of event (e.g., `backup`, `admin_action`, `login`)
- `timestamp` — ISO 8601 format
- `actor` — who performed the action (admin ID, system, etc.)
- `details` — additional context-specific data

Audit events are emitted to the Telegram assistant and stored in the audit log.

### Audit retention

Audit events are retained according to policy, typically:
- 90 days for operational events
- 1 year for administrator actions
- Indefinite for security-critical events

### Viewing audit events

1. Navigate to Admin → Events tab
2. Filter by event type, date range, or actor
3. Export events if needed

## Telegram Assistant

### Assistant lifecycle

The Telegram assistant is started during application startup and runs as a background
thread. It processes incoming updates and handles confirmed mutations.

### Starting/stopping

- The assistant starts automatically when `MCP_SERVER_ENABLED` is true
- It runs as an in-process thread alongside the Flask app

### Assistant events

Key assistant events include:

- `startup_backup_created` — backup created during startup
- `startup_backup_failed` — backup failed during startup
- `scheduled_backup_created` — daily scheduled backup created
- `scheduled_backup_failed` — daily scheduled backup failed
- `telegram_webhook_sync` — Telegram webhook synchronized on startup

### Assistant configuration

The assistant can be configured via environment variables:

- `MCP_SERVER_ENABLED` — whether the MCP server and assistant are enabled
- `MCP_SERVER_HOST` — MCP server host address
- `MCP_SERVER_PORT` — MCP server port

### Assistant operator health

Operators can inspect assistant queue/failure interpretation and cross-worker limits through the session-admin-only `GET /admin/assistant-health` endpoint. Counters are process-local and multiply across WSGI workers; saturation, provider/tool failures, delivery failures, and restart behavior are documented there.

### Platform notifications

Backup state events (database and image backups) and scheduled backup creation/failure are emitted as structured audit events and surfaced to the Telegram assistant. Delivery failures are deduplicated and do not undo committed actions.

### Assistant model safeguards

The assistant enforces bounded context/input/output budgets using serialized UTF-8 byte counting, provider `max_tokens`, and credential scrubbing across model payloads, history writes, tool errors, confirmation displays, and logs. Oversized or credential-bearing input fails safely without consuming unrelated confirmations.

## Member onboarding

### Telegram linking

Members can link their Telegram account to their ManaVote account:

1. Navigate to Settings → Telegram
2. Click "Link Telegram"
3. Follow the bot's instructions: type `/link` in Telegram
4. The bot will prompt for confirmation

### Unlinking Telegram

Members can unlink their Telegram account:

1. Navigate to Settings → Telegram
2. Click "Unlink Telegram"
3. Confirm the action

### Link state

- `last_linked_at` — timestamp when Telegram was last linked
- `last_unlinked_at` — timestamp when Telegram was last unlinked
- These are stored in the `members` table and used for diagnostics

## Password management

### Changing password

1. Navigate to Settings → Password
2. Enter current password
3. Enter new password
4. Confirm new password
5. Click "Save"

### Password requirements

- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 number
- At least 1 special character
- Cannot be the same as previous 5 passwords

### Password reset

If you forget your password:

1. Navigate to the login page
2. Click "Forgot password"
3. Enter your registered email or username
4. Follow the reset link sent to your email

**Note**: Password reset uses the email on file. If you no longer have access to your email,
contact an administrator.

## API rate limiting

Rate limits are defined per surface in [`APIDOC.md`](APIDOC.md) and [`interfaces/REST.md`](interfaces/REST.md).
Rate limit exceeded responses include:

- HTTP 429 status code
- `Retry-After` header indicating how long to wait
- Error envelope with code `-32003` (rate limited)

## Emergency procedures

### Database corruption

If database corruption is suspected:

1. Stop the application
2. Restore from the most recent backup
3. Verify integrity with `python -c "import sqlite3; conn = sqlite3.connect('app.db'); conn.execute('PRAGMA integrity_check');"`
4. Restart the application
5. Investigate the cause and update monitoring

### Complete failure

If the application fails to start:

1. Check environment variables are set correctly
2. Verify the database file exists and is not corrupted
3. Check that all required directories exist and are writable
4. Review the startup summary for degraded reasons
5. Consult the `tests/test_app_startup.py` tests for common startup issues

### Security incident

If a security incident is suspected:

1. Revoke all active sessions
2. Rotate all secrets (admin key, API keys, passwords)
3. Restore from backup if data integrity is suspect
4. Review audit logs for suspicious activity
5. Notify relevant stakeholders
6. Update monitoring to prevent recurrence

---
*Last updated: 2026-11-23*

For additional assistance, refer to the Telegram assistant or contact the system administrator.*