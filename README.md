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

### Budget lifecycle
- Budget is derived from `budget_log` (`SUM(amount)`).
- Proposals that meet voting threshold:
  - become `approved` if budget is sufficient,
  - become `over_budget` if budget is insufficient.
- `over_budget` proposals are auto-approved later when budget allows.
- Admin can undo approvals to restore budget.

### Dashboard and calendar
- Dashboard includes filters for status and categories.
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
docker-compose up --build
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

## Default credentials
- Username: `admin`
- Password: `carpediem42`

> On first login, admin is prompted to change the default password.

## Configuration
Environment variables are read from `.env` (see `sample.env`).

| Variable | Default | Purpose |
|---|---:|---|
| `FLASK_DEBUG` | `false` | Flask debug mode |
| `FLASK_CSRF` | `true` | Flask-WTF CSRF toggle (note: templates currently inject an empty `csrf_token`) |
| `FLASK_SECURE_COOKIES` | `false` | Enables `SESSION_COOKIE_SECURE` |
| `ADMIN_API_KEY` | _empty_ | Required for REST API endpoints |
| `TELEGRAM_BOT_TOKEN` | _empty_ | Telegram integration token |
| `TELEGRAM_CHAT_ID` | _empty_ | Telegram target chat |

## REST API
All API endpoints require `X-Admin-Key: <ADMIN_API_KEY>`.

Implemented endpoints:
- `POST /api/register`
- `POST /api/proposals`
- `PUT|PATCH /api/proposals/<proposal_id>`

See [APIDOC.md](APIDOC.md) for request/response details.

## Project structure

- `app/web/routes/main_routes.py` — routes, app setup, and request orchestration.
- `app/services/` — business logic helpers (auth/budget/proposal/admin/vote).
- `app/repositories/` — DB access helpers.
- `app/db/` — schema + migrations + DB connection helper.
- `templates/` — server-rendered HTML (Jinja2).
- `tests/` — unit and functional tests.

## Testing
```bash
pytest -q
```
