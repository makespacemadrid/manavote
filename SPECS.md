# SPECS: Detailed Code Review & Behavioral Specification

This document captures the **observed behavior** of the current codebase (`app.py` + templates), including architecture, business rules, API contracts, and notable gaps discovered during review.

---

## 1) System Architecture

- **Framework**: Flask monolith (`app.py`) with server-rendered Jinja templates.
- **Database**: SQLite (`hackerspace.db`) with direct SQL (no ORM).
- **State & auth**: Cookie-based Flask sessions (`session[member_id|username|is_admin]`).
- **Notifications**: Telegram Bot API via `requests.post`.
- **File uploads**: Proposal images in `static/uploads/`.

### Startup behavior
When run directly (`python app.py`):
1. Initializes DB schema and default values.
2. Checks over-budget proposals for possible auto-approval.
3. Starts Flask in debug mode on `0.0.0.0:5000`.

---

## 2) Data Model (SQLite)

### `members`
- `id` PK
- `username` unique, required
- `password_hash` required (SHA-256 hex)
- `is_admin` integer (0/1)
- `created_at`

### `proposals`
- `id` PK
- `title`, `description`, `amount`
- `url` optional
- `image_filename` optional
- `created_by` (member id)
- `created_at`
- `status` (`active`, `approved`, `over_budget` observed)
- `processed_at`
- `basic_supplies` integer (0/1)

### `votes`
- `id` PK
- `proposal_id`, `member_id`, `vote`
- `created_at`
- uniqueness on `(proposal_id, member_id)`

### `comments`
- `id` PK
- `proposal_id`, `member_id`, `content`, `created_at`

### `budget_log`
- `id` PK
- `amount`
- `description`
- `created_at`

### `settings`
- `key` PK
- `value`
- Used keys: `current_budget`, `monthly_topup`, `threshold_basic`, `threshold_over50`, `threshold_default`, `registration_enabled`

---

## 3) Initialization Defaults

On first run (if absent):
- Default admin user:
  - username: `admin`
  - password: `carpediem42`
- Settings:
  - `current_budget = 300`
  - `monthly_topup = 50`
  - `threshold_basic = 5`
  - `threshold_over50 = 20`
  - `threshold_default = 10`
  - `registration_enabled = true`
- Budget log seed entry: `+300` (`Initial budget`)

Schema migration helpers attempt to add `url` and `image_filename` columns with broad `except: pass` fallback.

---

## 4) Business Rules (Observed)

## Voting threshold formula
For each proposal, required net support (`min_backers`) is:
- `max(1, int(member_count * threshold%))`

Threshold chosen by:
1. `basic_supplies == 1` => `threshold_basic`
2. Else if `amount > 50` => `threshold_over50`
3. Else => `threshold_default`

## Approval condition
A proposal is approved iff both are true:
1. `net_votes = in_favor - against` is `>= min_backers`
2. `proposal.amount <= current_budget`

Effects on approval:
- status => `approved`
- `processed_at` set to now
- current budget decremented by amount
- budget log entry with negative amount
- Telegram approval message attempt

## Over-budget condition
If votes meet threshold but amount exceeds budget:
- status => `over_budget`
- `processed_at` set

Over-budget proposals are rechecked and auto-approved (FIFO by `created_at`) when budget becomes sufficient.

---

## 5) HTTP Surface

## Web routes
- `/` -> redirects to `/login` or `/dashboard`
- `/login` GET/POST
- `/logout`
- `/register` GET/POST (subject to `registration_enabled`)
- `/about`
- `/dashboard` (auth required)
- `/proposal/new` GET/POST (auth required)
- `/proposal/<id>` GET/POST (auth required; vote + comment)
- `/proposal/<id>/edit` GET/POST (auth required; owner or admin; active only)
- `/vote/<id>` POST quick-vote (auth required)
- `/comment/<id>/edit` GET/POST (admin only)
- `/comment/<id>/delete` POST (admin only)
- `/undo/<proposal_id>` (admin only)
- `/admin` GET/POST (admin only)
- `/check-overbudget` (publicly callable)

## API routes (X-Admin-Key)
- `POST /api/register`
- `POST /api/proposals`
- `PUT|PATCH /api/proposals/<id>`

All API routes return JSON and enforce `ADMIN_API_KEY` presence + header check.

---

## 6) Security Review Findings

### High priority
1. **Hardcoded default admin credential** (`admin` / `carpediem42`) created automatically.
2. **Password hashing uses unsalted SHA-256**, unsuitable for password storage; should use `werkzeug.security` or Argon2/bcrypt.
3. **No CSRF protection** on form POST actions (login, voting, admin actions).
4. **Debug mode enabled in app entrypoint** (`debug=True`) and binds all interfaces.

### Medium priority
5. **No rate limiting / brute-force controls** on login/API.
6. **Upload validation by extension only**, no MIME/content verification.
7. **Broad `except:` blocks** in DB migration and Telegram send suppress root cause visibility.
8. **`/check-overbudget` is unauthenticated**, allowing external triggering of processing loop.

---

## 7) Correctness & Logic Findings

1. **Monthly top-up mismatch**: admin action `trigger_monthly` uses hardcoded `50` instead of `settings.monthly_topup`.
2. **Duplicate/misleading flash in `add_budget`**: after add-budget action, an extra flash says monthly top-up triggered.
3. **Amount parsing lacks validation guards** on form handlers (`float(request.form["amount"])`) for malformed input.
4. **Connection nesting risk**: `process_proposal()` opens a new DB connection while some callers still hold another connection; works often in SQLite but can increase lock-contention risk.
5. **No status guard in quick vote insert path** before writing vote (vote accepted then checks status for processing).

---

## 8) Performance & Maintainability Findings

1. **N+1 query pattern on dashboard**: per-proposal counts and user-vote queries.
2. **Single-file monolith** (`app.py`) mixes routing, business logic, persistence, and integration concerns.
3. **Repeated threshold formula logic** appears in multiple functions.
4. **No automated tests** observed in repository.

---

## 9) Recommended Next Changes (Prioritized)

1. Replace password hashing with `generate_password_hash` / `check_password_hash`.
2. Remove hardcoded default admin password; require bootstrap env or one-time setup flow.
3. Disable debug mode by default; gate via env var.
4. Add CSRF protection (`Flask-WTF` or token middleware).
5. Fix admin action bugs:
   - use `monthly_topup` setting in `trigger_monthly`
   - remove incorrect extra flash in `add_budget`
6. Add strict input validation (amount parsing, URL checks, vote enum checks).
7. Restrict `/check-overbudget` to admin or remove route and run scheduled job.
8. Consolidate proposal-vote aggregate queries to reduce N+1 load.
9. Extract modules: `auth.py`, `budget.py`, `proposals.py`, `api.py`, `db.py`.
10. Add tests for approval rules, thresholds, over-budget queueing, and API auth.

---

## 10) Traceability Notes

This SPECS file describes what the code **currently does**, not an idealized future architecture. It can be used as a baseline for refactoring and for validating that future changes do not alter core voting/budget semantics unintentionally.
