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

## 3) Runtime behavior

At startup (`python app.py`):
1. App initializes DB path and upload folder.
2. DB tables are created if missing.
3. Default admin/settings are seeded if needed.
4. Migrations run (`app/db/migrations.py`).
5. Flask starts on host `0.0.0.0`, port `5000`.

Container runtime (`docker compose up --build`):
1. Compose builds from `Dockerfile` and starts the `web` service.
2. `.env` is loaded through `env_file`.
3. `app.db` and `static/uploads` are bind-mounted for persistence.
4. App is exposed on `http://localhost:5000`.

## 4) Data model

### `members`
- `id`, `username` (unique), `password_hash`, `is_admin`, `created_at`

### `proposals`
- `id`, `title`, `description`, `amount`, `url`, `image_filename`, `created_by`, `created_at`, `status`, `processed_at`, `over_budget_at`, `purchased_at`, `basic_supplies`
- `status ∈ {active, approved, over_budget}`

### `votes`
- `id`, `proposal_id`, `member_id`, `vote`, `created_at`
- Unique pair: `(proposal_id, member_id)`

### `comments`
- `id`, `proposal_id`, `member_id`, `content`, `created_at`

### `activity_log`
- `id`, `amount`, `description`, `created_by`, `created_at`

### `settings`
- `key`, `value`

Default seeded settings:
- `current_budget = 300` (legacy key; runtime budget is derived from `activity_log`)
- `monthly_topup = 50`
- `threshold_basic = 5`
- `threshold_over50 = 20`
- `threshold_default = 10`
- `registration_enabled = true`

## 5) Authentication and sessions

- Session-based auth.
- Session lifetime: 30 days (`PERMANENT_SESSION_LIFETIME`).
- Login is rate-limited (`5 per minute`).
- Password hashes use Werkzeug helpers; legacy SHA-256 hashes are migrated on login.
- Initial admin account is bootstrapped from `ADMIN_BOOTSTRAP_PASSWORD` when no admin exists.

## 6) Business rules

### 6.1 Threshold calculation
`min_backers = max(1, int(member_count * threshold_percent / 100))`

Threshold selection:
1. `basic_supplies == 1` ⇒ `threshold_basic`
2. `amount > 50` ⇒ `threshold_over50`
3. otherwise ⇒ `threshold_default`

### 6.2 Approval criteria
A proposal is approvable when both are true:
1. `net_votes = in_favor - against >= min_backers`
2. `amount <= current_budget` (where current budget = sum of `activity_log`)

### 6.3 Proposal lifecycle
- New proposal starts `active`.
- If threshold reached and budget available: `approved`, budget log gets negative entry.
- If threshold reached but budget unavailable: `over_budget`. When marked over_budget, `over_budget_at` timestamp is set.
- Over-budget proposals are reconsidered and auto-approved when funds appear.
- Admin can undo approval, returning status to `active` and restoring budget.

### 6.4 Basic supplies guardrail
If a proposal marked basic supplies has amount > €20, basic flag is auto-removed and a comment is inserted.

## 7) UI/feature behavior

### Dashboard
- Proposal list with status/category filters.
- Inline quick voting.
- Purchase confirmation actions for approved proposals.
- Budget history table with running balance.

### Calendar page
- Budget-over-time chart + activity table.
- Sorting and pagination (`20` rows/page across proposals + budget logs).

Chart datasets:
- **Budget Balance**: cyan line
- **Committed**: orange line
- **Cash In**: green bar
- **Cash Out**: red bar
- **Proposals (Being Voted)**: pink bar (`#ff69b4`)
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

## 8) HTTP routes

### Public
- `GET /`
- `GET|POST /login`
- `GET|POST /register` (if enabled)

### Authenticated member
- `GET /dashboard`
- `GET /calendar`
- `GET /about`
- `GET /logout`
- `GET /set-language/<lang>`
- `GET|POST /change-password`
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

### Admin web actions
- `GET|POST /admin`
- `GET /undo/<proposal_id>`
- `GET /check-overbudget`

### Admin-key REST API
- `POST /api/register`
- `POST /api/proposals`
- `PUT|PATCH /api/proposals/<proposal_id>`

## 9) Security notes

- Secure cookie flags are configurable (`FLASK_SECURE_COOKIES`, default enabled).
- CSRF is enforced via Flask-WTF `CSRFProtect` for browser form routes.
- API endpoints are explicitly CSRF-exempt and protected by `X-Admin-Key`.
- Rate limits enabled for login/API registration.
- API endpoints require `X-Admin-Key` and return `503` if API key is not configured.
- `SECRET_KEY` must be provided as a non-default value when running with `FLASK_ENV=production`.
- Uploaded images are stored locally under `static/uploads/`.

## 10) Known implementation notes

- `current_budget` exists in settings for backward compatibility, while live balance is computed from `activity_log`.
- Auto-backup runs every 24 hours via APScheduler when the app starts, pruning backups older than 7 days.
- `/healthz` returns service liveness for container health checks.

## 11) Backup

- Manual: Admin page includes "Backup Database" button.
- Auto: APScheduler runs `backup_db()` every 24 hours (if APScheduler is installed).
- Prunes: Backups older than `keep_days` (default 7) are removed.
- Filename format: `{db_name}_{timestamp}.db` (e.g., `app_20260426_120000.db`).
