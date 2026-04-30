# Hackerspace Budget Voting System

A Flask + SQLite application for managing budget proposals in a hackerspace.

## What it does

- Members can create, discuss, and vote on proposals.
- Proposals are auto-processed based on vote thresholds and available budget.
- Admins can manage members, thresholds, settings, and budget movements.
- API endpoints allow admin-key-based automation for member/proposal creation.
- UI supports English and Spanish.

## Core features

### Proposals and voting
- Create proposals with title, description, amount, optional URL, optional image, and basic-supplies flag.
- Proposal creator gets an automatic `in_favor` vote on web-created proposals.
- Vote options: `in_favor` / `against`.
- Votes are upserted (one vote per member per proposal).
- Active proposals can be edited/deleted by creator or admin.
- Approved proposals can be marked/unmarked as purchased.
- Undo approval button available for admins (restores budget, clears timestamps).
- Vote thresholds: Basic=5%, Standard=10%, Expensive=20% of member count (percentages, not absolute numbers).

### Timezone support
- Configurable timezone via admin panel (default: Europe/Madrid).
- All datetime displays automatically convert to configured timezone.
- Supported timezones: UTC, Europe/London, Europe/Paris, Europe/Madrid, America/New_York, America/Chicago, America/Los_Angeles, Asia/Tokyo, Asia/Shanghai, Australia/Sydney.

### Budget lifecycle
- Budget is derived from `activity_log` (`SUM(amount)`).
- Proposals that meet voting threshold:
  - become `approved` if budget is sufficient (Telegram notification sent),
  - become `over_budget` if budget is insufficient (tracks `over_budget_at` timestamp).
- `over_budget` proposals are auto-approved later when budget allows.
- Admin can undo approvals to restore budget, clearing `processed_at` and `purchased_at` timestamps.
- Approved proposals can be marked as `purchased` with timestamp.
- Monthly top-up defaults to €50 with description "Subvención mensual MakeSpace para juguetes nuevos".

### Dashboard and calendar
- Dashboard includes Budget card with current budget, member count, and vote requirements.
- Filter buttons show amounts (no decimals) with color-coded styling (All=white, Active=cyan, Approved/Pending Purchase=green, Pending Budget=light blue).
- Tags displayed left of proposal title (Basic=Bronze, Standard=Silver, Expensive=Gold).
- Vote counts show "X votes out of Y required" with green color for in-favor votes.
- Proposals card contains filters, proposal list, and vote buttons.
- Calendar includes an activity table and a "Budget Over Time" Chart.js chart.
- Budget chart datasets:
  - Budget Balance (cyan line)
  - Committed (orange line)
  - Cash In (green bar)
  - Cash Out (red bar)
  - Proposals (Being Voted) (pink bar)
  - Proposals (Approved) (purple bar)
- Committed series semantics:
  - `Committed = cash_balance - pending_over_budget_total`.
  - Positive values represent budget left after currently pending over-budget commitments.
  - Negative values represent budget debt (pending commitments exceed available balance).
  - Budget/Committed line datasets use separate Chart.js stack keys so lines are not cumulatively stacked with each other, while bar datasets remain stacked.

## Quick start

### Docker
```bash
cp sample.env .env
docker compose up --build
```

### Local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp sample.env .env
python app.py
```

App runs on `http://localhost:5000`.

## Initial admin bootstrap
- Username: `admin`
- Password: set via `ADMIN_BOOTSTRAP_PASSWORD` on first startup (required when no admin exists)

## Configuration
Environment variables are read from `.env` (see `sample.env`).

When running with Docker Compose:
- `.env` is loaded via `env_file`.
- Persistent data is mounted for `app.db` and `static/uploads`.

| Variable | Default | Purpose |
|---|---:|---|
| `FLASK_ENV` | _empty_ | Set to `production` to enable production-safe checks |
| `SECRET_KEY` | _empty_ | Required when `FLASK_ENV=production`; used for session + CSRF signing |
| `FLASK_DEBUG` | `false` | Flask debug mode |
| `FLASK_CSRF` | `true` | Flask-WTF CSRF protection toggle (enabled by default) |
| `FLASK_SECURE_COOKIES` | `true` | Enables `SESSION_COOKIE_SECURE` (recommended default) |
| `ADMIN_BOOTSTRAP_PASSWORD` | _empty_ | Required for first-time admin creation when DB has no admin user |
| `ADMIN_API_KEY` | _empty_ | Required for REST API endpoints |
| `TELEGRAM_BOT_TOKEN` | _empty_ | Telegram integration token |
| `TELEGRAM_CHAT_ID` | _empty_ | Telegram target chat |
| `TELEGRAM_THREAD_ID` | _empty_ | Optional Telegram topic/thread id for forum chats |

Additional operational notes:
- Web forms are protected with Flask-WTF `CSRFProtect`.
- API endpoints under `/api/*` are CSRF-exempt and authenticated with `X-Admin-Key`.
- Docker image runs as a non-root user.
- Health endpoint available at `GET /healthz` (used by compose healthcheck).
- Set `SECRET_KEY` and `ADMIN_BOOTSTRAP_PASSWORD` in production deployments.

## REST API
All API endpoints require `X-Admin-Key: <ADMIN_API_KEY>`.

Implemented endpoints:
- `POST /api/register`
- `POST /api/proposals`
- `PUT|PATCH /api/proposals/<proposal_id>`

See [APIDOC.md](APIDOC.md) for request/response details.

## Project structure

- `app/web/routes/main_routes.py` — routes, app setup, and request orchestration.
- `app/services/` — business logic helpers (auth/budget/proposal/admin/vote/backup).
- `app/repositories/` — DB access helpers.
- `app/db/` — schema + migrations + DB connection helper.
- `templates/` — server-rendered HTML (Jinja2).
- `tests/` — unit and functional tests.

## Backup

- Manual: Admin → Budget → "Backup Database" button
- Auto: Runs every 24 hours via APScheduler (if installed), keeps last 7 backups
- Backup files: `app.db`

## Testing
```bash
pytest -q
```

## Additional documentation
- Technical specification: [`SPEC.md`](SPEC.md)
