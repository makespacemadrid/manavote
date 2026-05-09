# Hackerspace Budget Voting System — Specification

## 1) Overview

Hackerspace Budget Voting is a Flask web app that lets members propose purchases, vote, and track budget usage over time.

Primary goals:
- Transparent spending decisions.
- Automatic approval logic based on configurable thresholds.
- Visibility into cash flow and pending commitments.

## 2) Technology

- Python + Flask (server-rendered Jinja2 templates)
- SQLite database
- Chart.js for budget visualization
- Optional Telegram notifications for proposal events
- Optional Telegram notifications for proposals and poll announcements

## 3) Runtime behavior

At startup (`python app.py`):
1. Flask app is constructed in `app/web/app_setup.py` (config load, logging, extension init).
2. Startup policy validation is applied (`app/startup_policy.py`) for environment invariants (for example production secret requirements).
3. App factory delegates bootstrap orchestration to `app/startup.py::run_startup_steps(...)`.
4. DB tables are created/verified and migrations run before optional startup jobs.
5. Optional startup jobs (scheduler, auto-backup check) run based on environment runtime policy (`test` disables them).
6. Flask starts on host `0.0.0.0`, port `5000`.

Container runtime (`docker compose up --build`):
1. Compose builds from `Dockerfile` and starts the `web` service.
2. `.env` is loaded through `env_file`.
3. `app.db` and `static/uploads` are bind-mounted for persistence.
4. App is exposed on `http://localhost:5000`.

## 3.1) Codebase map

Primary modules and responsibilities:
- `app/startup.py` — deterministic startup orchestration (`run_startup_steps`) and backup-check helper.
- `app/startup_policy.py` — startup policy validation and env-specific runtime flags.
- `app/web/app_setup.py` — Flask app construction/config, logging, and extension initialization.
- `app/web/routes/main_routes.py` — web route orchestration and legacy-compatible endpoints.
- `app/web/routes/api_routes.py` — admin-key REST API endpoints.
- `app/services/` — business logic helpers (auth/budget/proposal/admin/vote/backup/settings).
- `app/repositories/` — DB access helpers.
- `app/db/` — schema, migrations, and DB connection helper.
- `app/mcp_server.py` — MCP JSON-RPC server for admin tooling (list/read/create operations).
- `templates/` — server-rendered HTML (Jinja2).
- `tests/` — unit and functional tests.

## 4) Data model

### `members`
- `id`, `username` (unique), `password_hash`, `is_admin`, `telegram_username` (nullable), `telegram_user_id` (nullable), `created_at`

### `proposals`
- `id`, `title`, `description`, `amount`, `url`, `image_filename`, `created_by`, `created_at`, `status`, `processed_at`, `over_budget_at`, `purchased_at`, `basic_supplies`
- `status ∈ {active, approved, over_budget, purchased}`
- `purchased_at` timestamp set when proposal is marked as purchased

### `votes`
- `id`, `proposal_id`, `member_id`, `vote`, `created_at`
- Unique pair: `(proposal_id, member_id)`

### `comments`
- `id`, `proposal_id`, `member_id`, `content`, `created_at`

### `activity_log`
- `id`, `amount`, `description`, `created_by`, `created_at`

### `settings`
- `key`, `value`

### `polls`
- `id`, `question`, `options_json`, `created_by`, `created_at`, `status`, `closes_at`
- `status ∈ {open, closed}`

### `poll_votes`
- `id`, `poll_id`, `member_id`, `option_index`, `created_at`
- Unique pair: `(poll_id, member_id)` (latest vote replaces prior vote)

Default seeded settings:
- `current_budget = 300` (legacy key; runtime budget is derived from `activity_log`)
- `monthly_topup = 50`
- `threshold_basic = 5` (percentage of member count)
- `threshold_over50 = 20` (percentage of member count)
- `threshold_default = 10` (percentage of member count)
- `registration_enabled = true`
- `timezone = Europe/Madrid` (used for datetime display conversion)

## 5) Authentication and sessions

- Session-based auth.
- Session lifetime: 30 days (`PERMANENT_SESSION_LIFETIME`).
- Login is rate-limited (`5 per minute`).
- Password hashes use Werkzeug helpers; legacy SHA-256 hashes are migrated on login.
- Initial admin account is bootstrapped from `ADMIN_BOOTSTRAP_PASSWORD` when no admin exists; in production, missing value is a startup error, while non-production falls back to an insecure default with warning.

## 6) Business rules

### 6.1 Threshold calculation
`min_backers = max(1, int(member_count * threshold_percent / 100))`

Threshold selection:
1. `basic_supplies == 1` ⇒ `threshold_basic` (default: 2)
2. `amount > 50` ⇒ `threshold_over50` (default: 8)
3. otherwise ⇒ `threshold_default` (default: 4)

### 6.2 Approval criteria
A proposal is approvable when both are true:
1. `net_votes = in_favor - against >= min_backers`
2. `amount <= current_budget` (where current budget = sum of `activity_log`)

### 6.3 Proposal lifecycle
- New proposal starts `active`.
- If threshold reached and budget available: `approved`, budget log gets negative entry, Telegram notification sent.
- If threshold reached but budget unavailable: `over_budget`. When marked over_budget, `over_budget_at` timestamp is set.
- Over-budget proposals are reconsidered and auto-approved when funds appear.
- Admin can undo approval, returning status to `active`, restoring budget, and clearing `processed_at` and `purchased_at` timestamps.

### 6.4 Basic supplies guardrail
If a proposal marked basic supplies has amount > €20, basic flag is auto-removed and a comment is inserted.

## 7) UI/feature behavior

### Dashboard
- Budget card with current budget, member count, and vote requirements display.
- Proposal list with status/category filters (filters inside Proposals card).
- Filter buttons show amounts (no decimals) with color-coded styling.
- Inline quick voting with vote counts and "votes out of Y required" display.
- Purchase confirmation actions for approved proposals.
- Tags (Basic=Bronze, Standard=Silver, Expensive=Gold) displayed left of title.
- Budget history table with running balance and horizontal scroll on mobile.
- All datetimes displayed in configured timezone (default: Europe/Madrid).

### Calendar page
- Budget-over-time chart + activity table.
- Sorting and pagination (`20` rows/page across proposals + budget logs).

Chart datasets:
- **Budget Balance**: white line
- **Pending Budget**: purple line
- **Cash In**: white bar
- **Cash Out**: gray bar
- **Proposals (Being Voted)**: pink bar (`#ff69b4`)
- **Proposals (Approved)**: dark blue bar (`#1a4a7a`)

Committed series behavior:
- `pending` accumulates from proposals when they go over_budget (tracked by `over_budget_at`).
- `pending` decreases when over_budget proposals get approved.
- `Committed = cash_balance - pending`.
- Values above `0` mean budget still available after pending commitments.
- Values below `0` represent "budget debt" (pending commitments exceed current budget).
- The line datasets (`Budget Balance`, `Committed`) use separate Chart.js stack keys so they do not stack on top of each other; bar datasets remain stacked.

### About page
- Content is fully localized (English/Spanish) via translation keys.
- Explains proposal lifecycle, threshold rules, funding model, and transparency expectations.
- Includes governance link to the public repository for proposing feature changes.

### Admin panel
- **Members tab**: Add/remove members, toggle admin role, change passwords, and view linked Telegram username/ID when available (including partial links where only one value exists).
- **Budget tab**: Trigger monthly top-up (€50, description: "Subvención mensual MakeSpace para juguetes nuevos"), add custom budget entries.
- **Settings tab**: Registration toggle, timezone selector (UTC, Europe/London, Europe/Paris, Europe/Madrid, America/New_York, America/Chicago, America/Los_Angeles, Asia/Tokyo, Asia/Shanghai, Australia/Sydney).
- **Timezone tab**: Configure display timezone for all datetime fields.
- **Backup tab**: Manual backup, list existing backups.
- **Telegram tab**: Configure base URL for proposal links.
- **Polls tab**:
  - create polls,
  - close/reopen polls,
  - delete polls,
  - set poll voting mode (`both`, `web_only`, `telegram_only`),
  - send poll announcement to Telegram chat,
  - send poll test announcement to `TELEGRAM_ADMIN_ID`.

### Polls page (`/polls`)
- Members vote in Telegram with inline poll buttons (or `/vote <poll_id> <option_number>` fallback).
- "Who voted what" displays linked Telegram usernames when available (from `/link`), and falls back to app usernames for unlinked accounts.
- If the current member is not linked to Telegram, page shows a `/link <app_username> <app_password>` reminder.
- Poll message interaction flow:
  1. Poll announcement shows a `Vote` button with callback `showvote:<poll_id>`.
  2. Webhook resolves open poll and edits message reply markup into option buttons.
  3. Option callbacks use `pollvote:<poll_id>:<option_index>` and are translated to the same backend vote path as `/vote`.
- Web voting can be disabled by admin via poll vote mode.
- Open polls accept votes; closed polls are read-only.
- Results are transparent by design (counts, horizontal bars, and voter-choice list are visible).

## 8) HTTP routes

### Public
- `GET /`
- `GET|POST /login`
  - Route is registered on the auth blueprint (`auth.login`) and also exposed via a legacy `login` endpoint alias for backward compatibility.
- `GET|POST /register` (if enabled)

### Authenticated member
- `GET /dashboard`
- `GET /calendar`
- `GET|POST /polls`
- `GET /about`
- `GET /logout`
- `GET /set-language/<lang>`
- `GET|POST /change-password`
- `GET|POST /telegram-settings`
  - `telegram_username` and `telegram_user_id` are read-only in UI.
  - Both fields are linked only from Telegram via `/link <app_username> <app_password>`.
- `GET|POST /proposal/new`
- `GET|POST /proposal/<proposal_id>`
- `GET|POST /proposal/<proposal_id>/edit`
- `POST /proposal/<proposal_id>/delete`
- `POST /vote/<proposal_id>`
- `GET|POST /withdraw-vote/<proposal_id>`
- `POST /comment/<comment_id>/edit`
- `POST /comment/<comment_id>/delete`
- `POST /purchase/<proposal_id>`
- `POST /unpurchase/<proposal_id>`

### Telegram integration
- `POST /telegram/webhook/<secret>` receives Telegram updates and processes `/vote` commands, `/link <app_username> <app_password>` account-linking commands, and inline-button `callback_query` votes.
- Poll inline callbacks:
  - `showvote:<poll_id>` expands message keyboard to option buttons.
  - `pollvote:<poll_id>:<option_index>` records vote.
- Webhook security requires `TELEGRAM_WEBHOOK_SECRET` to match `<secret>`.
- Vote-to-member mapping prefers `members.telegram_user_id`, then falls back to username matching against `members.username` and `members.telegram_username` (`username` or `@username`, case-insensitive).
- If no linked member is found but Telegram provides numeric user id, vote is stored under a deterministic negative `member_id` placeholder (`-telegram_user_id`) so one Telegram user still maps to one vote.
- Telegram client calls are considered successful only when HTTP status is `200` and Telegram API responds with `"ok": true` (when JSON is returned).

### Admin web actions
- `GET|POST /admin` (includes timezone selector, member management, budget controls, and poll actions)
- `GET /undo/<proposal_id>` (undo approval, restore budget, clear timestamps)
- `GET /check-overbudget`

### Admin-key REST API
- `POST /api/register`
- `POST /api/proposals`
- `GET /api/proposals` (supports `status`, `limit`, `offset`)
- `GET /api/proposals/<proposal_id>`
- `PUT|PATCH /api/proposals/<proposal_id>`
- `GET /api/polls`
- `POST /api/polls`
- `GET /api/members/telegram` (supports `include_unlinked`, `limit`, `offset`)

### MCP JSON-RPC tools (`/mcp`)
- Read/list tools:
  - `list_proposals` (optional `status`, `limit`, `offset`)
  - `current_budget`
  - `list_member_telegram_links` (optional `include_unlinked`, `limit`, `offset`)
- Create tools:
  - `create_member` (`username`, `password`, optional `is_admin`)
  - `create_proposal` (`title`, `amount`, `created_by`, optional `description`/`url`/`basic_supplies`)
  - `create_poll` (`question`, `options`, `created_by`)

## 9) Security notes

- Secure cookie flags are configurable (`FLASK_SECURE_COOKIES`, default enabled).
- CSRF is enforced via Flask-WTF `CSRFProtect` for browser form routes.
- API endpoints are explicitly CSRF-exempt and protected by `X-Admin-Key`.
- Rate limits enabled for login/API registration.
- API endpoints require `X-Admin-Key` and return `503` if API key is not configured.
- `SECRET_KEY` must be provided as a non-default value when running with `FLASK_ENV=production`.
- Uploaded images are stored locally under `static/uploads/`.
- Image upload validation uses signature-based sniffing (JPEG/PNG headers) in proposal create/edit flows; files failing signature checks are rejected.

## 10) Known implementation notes

- `current_budget` exists in settings for backward compatibility, while live balance is computed from `activity_log`.
- Auto-backup runs every 24 hours via APScheduler when the app starts (except in `FLASK_ENV=test`), pruning backups older than 7 days.
- `/healthz` returns service liveness for container health checks.
- Proposal vote audit logs use a shared schema with fields: `event`, `source`, `mode`, `proposal_id`, `member_id`, `vote`, `reason_code`, `latency_ms`.

## 11) Backup

- Manual: Admin page includes "Backup Database" button.
- Auto: APScheduler runs `backup_db()` every 24 hours (if APScheduler is installed).
- Prunes: Backups older than `keep_days` (default 7) are removed.
- Filename format: `{db_name}_{timestamp}.db` (e.g., `app_20260426_120000.db`).


## 12) Testing

Recommended commands:

```bash
pytest -q
```

Targeted startup/template guard checks:

```bash
pytest -q tests/test_production_config.py tests/test_template_guards.py

# Startup architecture reliability checks
pytest -q tests/test_app_startup.py tests/test_startup_policy.py tests/unit/test_settings_service.py tests/unit/test_vote_repository_contract.py
```

Coverage notes:
- Production config tests validate fail-fast behavior for missing/unsafe `SECRET_KEY` and missing `ADMIN_BOOTSTRAP_PASSWORD` under `FLASK_ENV=production`.
- Template guard tests validate top-nav partial usage and CSRF hidden input markup invariants in key templates.
- Startup tests validate deterministic bootstrap sequencing and warning/fail-fast boundaries.
- Startup policy tests validate env-specific runtime flags and production secret enforcement.
- Settings helper tests validate normalized enum-setting reads and fallback behavior.
- Vote repository contract tests validate upsert replacement and aggregate count invariants.
- API contract tests validate helper-level request/auth parsing, standardized error envelopes, and `/api/*` behavior for proposal/poll operations.


## 13) Proposal vote channels (Web / Telegram / Both)

- Config key: `proposal_vote_mode` with allowed values: `both`, `web_only`, `telegram_only` (default `both`).
- Web proposal votes are accepted only when mode allows Web (`both` or `web_only`).
- Telegram proposal votes are accepted only when mode allows Telegram (`both` or `telegram_only`).
- Telegram voting paths supported:
  - Text command: `/pvote <proposal_id> <yes|no>`
  - Inline callback payload: `pvote:<proposal_id>:yes|no`
- Both channels route through unified proposal vote ingestion with upsert semantics (latest vote wins per member/proposal).
- Rejected votes are logged with reason code (`channel_disabled`) for auditability.
