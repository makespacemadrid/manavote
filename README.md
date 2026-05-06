# Hackerspace Budget Voting System

A Flask + SQLite application for managing budget proposals in a hackerspace.


## Contents
- [What it does](#what-it-does)
- [Core features](#core-features)
- [Quick Start](#quick-start)
- [Setup and configuration](#setup-and-configuration)
- [REST API](#rest-api)
- [MCP server](#mcp-server)
- [Testing](#testing)

![Proposals](/static/img/proposals.png)
![Calendar](/static/img/calendar.png)

## What it does

- Members can create, discuss, and vote on proposals.
- Members can monitor progress from Dashboard and Calendar views.
- Proposals are auto-processed based on vote thresholds and available budget.
- Members can participate in transparent polls inside the web app.
- Members can view Telegram account-link details from Settings (Telegram username and Telegram user ID are read-only).
- Admins can manage members, thresholds, settings, and budget movements (including Telegram link visibility in Members table).
- UI supports English and Spanish.
- API endpoints allow admin-key-based automation for member/proposal creation, and MCP tools support admin JSON-RPC automation for proposals, budget, and Telegram link polling (see [`APIDOC.md`](APIDOC.md)).
- Quick reference: full REST + MCP API docs are in [`APIDOC.md`](APIDOC.md).

## Core features

### Proposals and voting
- Create proposals with title, description, amount, optional URL, optional image, and basic-supplies flag.
- Optional voting deadline can be included when sending proposal announcement to Telegram.
- Proposal creator gets an automatic `in_favor` vote on web-created proposals.
- Vote options: `in_favor` / `against`.
- Votes are upserted (one vote per member per proposal).
- Active proposals can be edited/deleted by creator or admin.
- Approved proposals can be marked/unmarked as purchased.
- Undo approval button available for admins (restores budget, clears timestamps).
- Vote thresholds: Basic=5%, Standard=10%, Expensive=20% of member count (percentages, not absolute numbers).

### Dashboard and calendar
- Navigation order in the top menu is: **Dashboard → Calendar → Polls**.
- Dashboard includes Budget card with current budget, member count, and vote requirements.
- Filter buttons show amounts (no decimals) with color-coded styling (All=white, Active=cyan, Approved/Pending Purchase=green, Pending Budget=purple).
- Tags displayed left of proposal title (Basic=Bronze, Standard=Silver, Expensive=Gold).
- Vote counts show "X votes out of Y required" with green color for in-favor votes.
- Proposals card contains filters, proposal list, and vote buttons.
- Calendar includes an activity table and a "Budget Over Time" Chart.js chart.
- Budget chart datasets:
  - Budget Balance (white line)
  - Pending Budget (purple line)
  - Cash In (white bar)
  - Cash Out (gray bar)
  - Proposals (Being Voted) (pink bar)
  - Proposals (Approved) (dark blue bar)
- Committed series semantics:
  - `Committed = cash_balance - pending_over_budget_total`.
  - Positive values represent budget left after currently pending over-budget commitments.
  - Negative values represent budget debt (pending commitments exceed available balance).
  - Budget/Committed line datasets use separate Chart.js stack keys so lines are not cumulatively stacked with each other, while bar datasets remain stacked.

### Polls
- Admins can create polls with 2..12 options from the Admin panel.
- Members can vote from Telegram by tapping inline poll buttons (or using `/vote <poll_id> <option_number>` as fallback).
- Members can pre-link Telegram identity with `/link <app_username> <app_password>` to bind Telegram account to their app member record. This command is the only way `telegram_username` and `telegram_user_id` are set.
- On `/polls`, the “Who voted what” list prefers linked Telegram usernames (from `/link`) and falls back to app usernames only when Telegram link data is missing.
- If your account is not linked, `/polls` shows a reminder banner with `/link <app_username> <app_password>`.
- Telegram poll announcements include a **Vote** button (`showvote:<poll_id>`) that expands into one button per option (`pollvote:<poll_id>:<index>`).
- Admins can restrict poll voting channel to `Web + Telegram`, `Web only`, or `Telegram only`.
- The app tracks and displays all poll state/results on `/polls`.
- Polls are transparent: the page shows totals, horizontal result bars, and “who voted what”.
- Polls can be closed/reopened by admins.
- Polls can be deleted by admins.
- Admins can send poll text to the main chat or as a test to `TELEGRAM_ADMIN_ID`.
- Telegram webhook endpoint: `POST /telegram/webhook/<TELEGRAM_WEBHOOK_SECRET>` (set secret in env and configure in BotFather webhook URL).
- Telegram API responses are treated as successful only when both HTTP status is `200` and JSON response contains `"ok": true`.

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

## Quick Start

See [`QUICKSTART.md`](QUICKSTART.md) for Docker and local setup instructions.

## Setup and configuration

Setup, initial admin bootstrap, environment variables, backup behavior, and testing commands are documented in [`QUICKSTART.md`](QUICKSTART.md).

## REST API
All API endpoints require `X-Admin-Key: <ADMIN_API_KEY>`.

Implemented endpoints:
- `POST /api/register`
- `POST /api/proposals`
- `GET /api/proposals/<proposal_id>`
- `PUT|PATCH /api/proposals/<proposal_id>`
- `GET /api/polls`
- `POST /api/polls`

See [APIDOC.md](APIDOC.md) for request/response details.

## MCP server

A lightweight MCP JSON-RPC server is available at `app/mcp_server.py`.

### Authentication
Set `MCP_API_KEY` and pass it on each MCP request as `params.api_key`.

### Run standalone (stdio)
```bash
python -m app.mcp_server
```

### Run alongside Flask app
Set:
- `MCP_SERVER_ENABLED=true`
- optional `MCP_SERVER_HOST` (default `127.0.0.1`)
- optional `MCP_SERVER_PORT` (default `8765`)

When enabled, `app.py` starts the MCP TCP server in a background thread.

Implemented tools:
- `list_proposals` (optional `status`, `limit`, `offset`)
- `current_budget`
- `list_member_telegram_links` (optional `include_unlinked`, `limit`, `offset`)


## Project structure

- `app/web/app_setup.py` — Flask app construction/config, logging, and extension initialization.
- `app/web/routes/main_routes.py` — routes and request orchestration.
- `app/services/` — business logic helpers (auth/budget/proposal/admin/vote/backup).
- `app/repositories/` — DB access helpers.
- `app/db/` — schema + migrations + DB connection helper.
- `templates/` — server-rendered HTML (Jinja2).
- `tests/` — unit and functional tests.

## Additional documentation
- Technical specification: [`SPEC.md`](SPEC.md)
- Product ideas / backlog: [`IDEAS.md`](IDEAS.md)

