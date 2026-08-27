# Hackerspace Budget Voting System — Specification

## 1) Overview

Hackerspace Budget Voting is a Flask web app that lets members propose purchases, vote, and track budget usage over time.

Primary goals:
- Transparent spending decisions.
- Automatic approval logic based on configurable thresholds.
- Visibility into cash flow and pending commitments.

## 2) Technology

- Python + Flask (routing, authentication, business logic, and server-rendered page content)
- React 19 + Vite (progressively hydrated application shell)
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
6. The Telegram webhook is synced with Telegram on startup (`sync_telegram_webhook_on_startup`); its result feeds into the overall startup `degraded` status.
7. Flask starts on host `0.0.0.0`, port `45000`.

Container runtime (`docker compose up --build`):
1. Compose builds the React assets in the Dockerfile Node stage, then assembles and starts the Flask `web` service.
2. `.env` is loaded through `env_file`.
3. `app.db` and `static/uploads` persist through named Docker volumes (`app_data:/data`,
   `uploads_data:/app/static/uploads`), not host bind mounts; `APP_DB_PATH` is set to
   `/data/app.db` inside the container.
4. App is exposed on `http://localhost:45000`.

## 3.1) Codebase map

Primary modules and responsibilities:
- `app/startup.py` — deterministic startup orchestration (`run_startup_steps`) and backup-check helper.
- `app/startup_policy.py` — startup policy validation and env-specific runtime flags.
- `app/web/app_setup.py` — Flask app construction/config, logging, and extension initialization.
- `app/web/routes/main_routes.py` — web route orchestration and legacy-compatible endpoints; most business logic not yet extracted into `app/services/` still lives here.
- `app/web/routes/api_routes.py` — admin-key REST API endpoints.
- `app/web/routes/admin_routes.py`, `auth_routes.py`, `group_purchase_routes.py`, `poll_routes.py`, `proposal_routes.py` — blueprint modules split out of `main_routes.py`; `auth_routes.py` also implements the Keycloak/OIDC SSO login flow.
- `app/web/routes/helpers/` — shared request/response helpers used across blueprints.
- `app/domain/` — `entities.py`, `enums.py` (e.g. `ProposalStatus`, live-wired into API/MCP validation), `exceptions.py`, `rules.py`.
- `app/services/` — business logic helpers (auth/budget/proposal/backup/settings/Telegram); `admin_service.py`, `vote_service.py`, and `app/domain/rules.py` are currently placeholder stubs, with the corresponding logic still in `main_routes.py`.
- `app/repositories/` — DB access helpers.
- `app/db/` — schema, migrations, and DB connection helper.
- `app/mcp_server.py` — MCP JSON-RPC server for admin tooling (list/read/create operations).
- `app/integrations/telegram_agent.py` — OpenAI-compatible conversation loop, MCP tool adapter, per-user history, and confirmed mutation workflow.
- `app/integrations/bounded_executor.py` — bounded background execution for model work.
- `app/integrations/telegram_client.py` — Telegram API transport, temporary status messages, callbacks, and long-response chunking.
- `app/integrations/telegram_webhook.py` — payload extraction, command dispatch, and bounded update-ID deduplication.
- `app/services/telegram_access_service.py` — live Telegram-ID allowlist and administrator principal lookup.
- `templates/` — server-rendered HTML and accessible pre-hydration markup (Jinja2).
- `frontend/src/` — React application-shell components, hydration entry point, and source styles.
- `static/react/` — Flask-served frontend assets; development fallbacks are replaced by the Vite production build.
- `vite.config.js` — deterministic frontend build output configuration.
- `tests/` — unit and functional tests.

## 4) Data model

### `members`
- `id`, `username` (unique), `password_hash`, `is_admin`, `telegram_username` (nullable), `telegram_user_id` (nullable), `created_at`
- `last_linked_at` (nullable), `last_unlinked_at` (nullable) — set whenever `telegram_user_id`
  is established/changed (via `/link` or an OIDC login whose claims carry a Telegram
  identity) or cleared (admin or member self-service unlink), for admin diagnostics
- `oidc_sub` (nullable, unique), `email` (nullable), `display_name` (nullable) — populated by Keycloak/OIDC SSO login (see §5)

### `proposals`
- `id`, `title`, `description`, `amount`, `url`, `image_filename`, `created_by`, `created_at`, `status`, `processed_at`, `over_budget_at`, `purchased_at`, `basic_supplies`
- `status ∈ {active, approved, over_budget, rejected}` (`ProposalStatus` in `app/domain/enums.py`).
  `rejected` is a valid filter value but no code path currently assigns it to a proposal.
- "Purchased" is not a `status` value: `purchased_at` is a separate timestamp set on an
  `approved` proposal when it is marked purchased, and cleared when unmarked

### `votes`
- `id`, `proposal_id`, `member_id`, `vote`, `created_at`
- Unique pair: `(proposal_id, member_id)`

### `comments`
- `id`, `proposal_id`, `member_id`, `content`, `created_at`

### `activity_log`
- `id`, `amount`, `description`, `created_by`, `created_at`, `proposal_id` (nullable, links a budget-log entry back to the proposal that generated it)

### `settings`
- `key`, `value`

### `polls`
- `id`, `question`, `options_json`, `created_by`, `created_at`, `status`, `closes_at`
- `status ∈ {open, closed}`

### `poll_votes`
- `id`, `poll_id`, `member_id`, `option_index`, `created_at`
- Unique pair: `(poll_id, member_id)` (latest vote replaces prior vote)

### Group purchases
- `group_purchases`: title, description, creator, deadline, product URL, image, payment method, and lifecycle status (`open`, `ordered`, `received`).
- `group_purchase_components`: named options with a unit price and stable display position.
- `group_purchase_quantities`: one requested quantity per member and component.
- `group_purchase_payments`: records that the purchase creator has received a participant's payment.
- `group_purchase_shared_costs`: shipping, taxes, or other costs allocated proportionally by each participant's selected-product value.

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
- Login is rate-limited (`5 per minute`). `/login` accepts either the account's
  `username` or its `email` (case-insensitive), matching by username first.
- Password hashes use Werkzeug helpers; legacy SHA-256 hashes are migrated on login.
- Initial admin account is bootstrapped from `ADMIN_BOOTSTRAP_PASSWORD` when no admin exists; in production, missing value is a startup error, while non-production falls back to an insecure default with warning.

### Keycloak / OIDC SSO

- Enabled whenever `OIDC_CLIENT_SECRET` is set; implemented in `app/web/routes/auth_routes.py` via Authlib's OAuth Authorization Code flow (`GET /auth/login/keycloak` → `GET /auth/callback/keycloak`), rate-limited (`10 per minute`).
- Sign-in requires the Keycloak group named by `OIDC_REQUIRED_GROUP` (default `members-active`) in the ID token's `groups` claim; missing it aborts with `403`. The `admins` group is synchronized into `is_admin` on every login, including removal.
- Member provisioning (`_upsert_oidc_member`) resolves an existing member by `oidc_sub` first; if none exists and the claims include an `email`, it looks up any existing member with `oidc_sub IS NULL` and a matching email (case-insensitive) and **silently attaches** the SSO identity to that account (updating `oidc_sub`, `email`, `display_name`, `is_admin`, and Telegram fields via `COALESCE`). Only when neither match exists is a new member created, with a numeric suffix applied on a username collision.
- Logout redirects through Keycloak's `end_session` endpoint only for sessions established via SSO (`session["oidc_login"]`); password-login sessions log out locally. Access/refresh tokens are discarded after the callback — the app makes no further Keycloak API calls.

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

### React application shell

- Flask remains the source of truth for routes, sessions, authorization, localization, and page data.
- Shared navigation is rendered by Jinja first, so links remain available without JavaScript, then hydrated by React using JSON props from `data-react-props`.
- The server and React markup must remain structurally equivalent to avoid hydration recovery and layout shifts.
- The active route is represented with `aria-current="page"`; the mobile menu exposes `aria-expanded` and `aria-controls` and closes on link selection or Escape.
- Vite writes fixed `app.js` and `style.css` filenames to `static/react`, matching the Flask base template.

### Proposals
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
- **Pending Budget**: purple line (`#9932CC`)
- **Budget In**: white bar
- **Budget Out**: gray bar
- **Proposals (Being Voted)**: light blue bar (`#87cefa`)
- **Proposals (Approved)**: purple bar (`#9932CC`)

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
- **Budget tab**: Trigger monthly top-up (€50, description: "Monthly top-up"), add custom budget entries.
- **Settings tab**: Registration toggle, timezone selector (UTC, Europe/London, Europe/Paris, Europe/Madrid, America/New_York, America/Chicago, America/Los_Angeles, Asia/Tokyo, Asia/Shanghai, Australia/Sydney).
- **Timezone tab**: Configure display timezone for all datetime fields.
- **Backup tab**: Manual backup, list existing backups.
- **Telegram tab**: Configure base URL for proposal links.
- **Polls tab**:
  - create polls (question 5..200 characters, 2..12 options each ≤120 characters,
    enforced identically by the web form, `POST /api/polls`, and the `create_poll`
    MCP tool),
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
- Polls can be created with an explicit end datetime (`closes_at`); expired open polls are auto-closed during active poll flows.
- When a poll closes (manual close or automatic expiry), the app posts a Telegram results summary including per-option totals, percentages, and a text bar-graph.
- Telegram poll/proposal announcement messages start with the poll question / proposal title as the first line.
- Results are transparent by design (counts, horizontal bars, and voter-choice list are visible).

### Group purchases page (`/group-purchases`)
- Any authenticated member can propose a shared purchase and add up to 30 option rows, each with its own name and unit price.
- A proposal may include a deadline, product URL, image, and payment instructions.
- The creator can add shared costs such as shipping or taxes. Each participant pays the same percentage of those costs as their percentage of the total selected-product value.
- Creating a proposal announces it in the configured Telegram group/thread, including its options and prices.
- The configured Telegram group/thread is notified again when the creator marks the order as placed and when the shipment is received.
- While the purchase is `open`, members can update their requested quantities and the creator can edit its details and option prices.
- The creator advances the lifecycle from `open` to `ordered`, then to `received`; quantities and prices are frozen once ordered.
- The page calculates the amount owed by every participant and lets the creator mark each payment as received.

## 8) HTTP routes

### Public
- `GET /`
- `GET|POST /login`
  - Route is registered on the auth blueprint (`auth.login`) and also exposed via a legacy `login` endpoint alias for backward compatibility.
  - Accepts either `username` or `email` (case-insensitive).
- `GET|POST /register` (if enabled)
- `GET /auth/login/keycloak`, `GET /auth/callback/keycloak` (Keycloak/OIDC SSO; see §5)

### Authenticated member
- `GET /proposals`
- `GET /budget`
- `GET|POST /polls`
- `GET|POST /group-purchases`
- `GET|POST /group-purchases/<purchase_id>/edit` (creator only while open)
- `POST /group-purchases/<purchase_id>/quantity`
- `POST /group-purchases/<purchase_id>/status` (creator only)
- `POST /group-purchases/<purchase_id>/payments/<member_id>` (creator only)
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
- `POST /comment/<comment_id>/edit` (admin-only; unlike proposal edit/delete, there is no owner exception)
- `POST /comment/<comment_id>/delete` (admin-only; unlike proposal edit/delete, there is no owner exception)
- `POST /purchase/<proposal_id>`
- `POST /unpurchase/<proposal_id>`

### Telegram integration
- `POST /telegram/webhook/<secret>` receives Telegram updates and processes `/vote`, `/pvote`, `/link <app_username> <app_password>`, `/help`, and `/reset`, inline-button callbacks, and optional natural-language messages.
- Poll inline callbacks:
  - `showvote:<poll_id>` expands message keyboard to option buttons.
  - `pollvote:<poll_id>:<option_index>` records vote.
- Webhook security requires `TELEGRAM_WEBHOOK_SECRET` to match `<secret>`.
- Vote-to-member mapping prefers `members.telegram_user_id`, then falls back to username matching against `members.username` and `members.telegram_username` (`username` or `@username`, case-insensitive).
- If no linked member is found but Telegram provides numeric user id, vote is stored under a deterministic negative `member_id` placeholder (`-telegram_user_id`) so one Telegram user still maps to one vote.
- Optional strict mode: when `telegram_require_linked_vote=true`, Telegram votes require a linked account match and unlinked users are instructed to run `/link <app_username> <app_password>`.
- Telegram client calls are considered successful only when HTTP status is `200` and Telegram API responds with `"ok": true` (when JSON is returned).
- Recent numeric Telegram `update_id` values are retained in a bounded, thread-safe cache; retries are acknowledged without repeating commands, votes, model calls, or MCP actions.

#### Natural-language assistant flow

1. Natural-language handling is enabled only when `OCABRA_CHAT_URL` and `MCP_API_KEY` are configured.
2. In private chats, every non-command message qualifies. In groups, a message only
   qualifies when it addresses the bot: an `@mention`/`bot_command` entity matching
   `TELEGRAM_BOT_USERNAME`, a reply to one of the bot's own messages, or being posted in
   the admin-configured forum topic (`TELEGRAM_CHAT_ID` + `TELEGRAM_THREAD_ID`), which is
   treated as an always-on assistant conversation. Leaving `TELEGRAM_BOT_USERNAME` unset
   while group privacy mode is disabled makes this matching overly permissive; startup
   logs `missing_bot_username_for_group` when it detects that configuration.
3. The sender's numeric Telegram ID is resolved from `members.telegram_user_id` for every message. Unknown IDs are ignored before worker admission; link/unlink and admin changes therefore apply immediately.
4. The bot posts `🤔 Thinking…`, then submits the model request to a four-worker queue with at most 32 pending requests. Saturated queues return a retry message rather than growing without bound.
5. The OpenAI-compatible model receives MCP function schemas. Members receive read-only proposal, poll, group-purchase, budget, and voting-setting tools; administrators receive the complete MCP tool set.
6. Read tools execute in-process through the MCP JSON-RPC handler. Mutating tools create a per-chat/per-user pending action instead of executing immediately.
7. A linked administrator must send `/confirm` before `TELEGRAM_CONFIRM_TTL_SECONDS` expires; `/cancel` discards it. `/reset` clears that user's history and pending action.
8. The final answer is split into chunks of at most 3900 characters. The temporary thinking message is deleted after delivery or worker failure.

Conversation history, pending confirmations, and update deduplication are stored in
SQLite (`telegram_conversation_history`, `telegram_pending_actions`,
`telegram_update_dedup`) and shared across application workers, surviving restarts.
History is bounded to the most recent 12 turns per chat/user. The bounded model-request
worker queue itself remains process-local — it limits concurrent model calls within one
process and is not yet shared across workers.

### Admin web actions
- `GET|POST /admin` (includes timezone selector, member management, budget controls, and poll actions)
- `GET /undo/<proposal_id>` (undo approval, restore budget, clear timestamps)
- `GET /check-overbudget`

### Admin-key REST API
- `POST /api/register`
- `POST /api/proposals`
- `GET /api/proposals` (supports domain `status` values, `age=recent|old`, `limit`, `offset`; age filters select active proposals around the 30-day boundary)
- `GET /api/proposals/<proposal_id>`
- `PUT|PATCH /api/proposals/<proposal_id>`
- `GET /api/polls`
- `POST /api/polls`
- `GET /api/members/telegram` (supports `include_unlinked`, `limit`, `offset`)
- `GET /api/members/statistics` (lifetime per-user participation and financial statistics; includes page `count` and matching `total`; email requires `include_email=true`)
- `GET /api/settings/voting`
- `PUT|PATCH /api/settings/voting`

### MCP JSON-RPC tools (`/mcp`)
- Read/list tools:
  - `list_proposals` (optional `status`, `age=recent|old`, `limit`, `offset`; age filters select active proposals around the 30-day boundary)
  - `current_budget`
  - `list_member_telegram_links` (optional `include_unlinked`, `limit`, `offset`)
  - `list_user_statistics` (optional `limit`, `offset`, `username`, sorting, and opt-in `include_email`; includes matching `total`)
- Create tools:
  - `create_member` (`username`, `password`, optional `is_admin`)
  - `create_proposal` (`title`, `amount`, `created_by`, optional `description`/`url`/`basic_supplies`)
  - `create_poll` (`question`, `options`, `created_by`)

## 9) Security notes

- Secure cookie flags are configurable (`FLASK_SECURE_COOKIES`, default `false`, `true` when `FLASK_ENV=production`).
- CSRF is enforced via Flask-WTF `CSRFProtect` for browser form routes.
- API endpoints are explicitly CSRF-exempt and protected by `X-Admin-Key`.
- Rate limits enabled for login/API registration.
- API endpoints require `X-Admin-Key` and return `503` if API key is not configured.
- `SECRET_KEY` must be provided as a non-default value when running with `FLASK_ENV=production`.
- Uploaded images are stored locally under `static/uploads/`.
- Image upload validation uses signature-based sniffing (JPEG/PNG headers) in proposal create/edit flows; files failing signature checks are rejected.

## 10) Known implementation notes

Operator-facing startup states, structured event sequences, stable reason-code meanings,
and troubleshooting actions are defined in [`OPERATIONS.md`](OPERATIONS.md). This
specification defines application behavior; the operations guide defines how to diagnose
that behavior without exposing prompts, credentials, or provider payloads.

- `current_budget` exists in settings for backward compatibility, while live balance is computed from `activity_log`.
- Auto-backup runs every 24 hours via APScheduler when the app starts (except in `FLASK_ENV=test`), pruning backups older than 7 days.
- `/healthz` returns service liveness for container health checks.
- Proposal vote audit logs use a shared schema with fields: `event`, `source`, `mode`, `proposal_id`, `member_id`, `vote`, `reason_code`, `latency_ms`.

## 11) Backup

- Manual: Admin page includes "Backup Database" button.
- Auto: APScheduler runs `backup_db()` and `backup_uploads()` (for `static/uploads/`) every 24 hours (if APScheduler is installed).
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
- Config key: `telegram_require_linked_vote` with allowed values: `true`, `false` (default `false`).
- Web proposal votes are accepted only when mode allows Web (`both` or `web_only`).
- Telegram proposal votes are accepted only when mode allows Telegram (`both` or `telegram_only`).
- Telegram voting paths supported:
  - Text command: `/pvote <proposal_id> <yes|no>`
  - Inline callback payload: `pvote:<proposal_id>:yes|no`
- Both channels route through unified proposal vote ingestion with upsert semantics (latest vote wins per member/proposal).
- Rejected votes are logged with reason code (`channel_disabled`) for auditability.
