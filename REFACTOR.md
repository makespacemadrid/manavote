# REFACTOR Plan

This document defines a phased, low-risk refactor plan for the current Flask budget voting app.

## Goals
- Preserve existing behavior while improving security, reliability, and maintainability.
- Break the monolith (`app.py`) into testable modules.
- Add automated tests around budget/voting rules before high-impact changes.

## Non-goals
- No immediate UI redesign.
- No change to core product semantics (thresholds, net-vote logic, over-budget queue) unless explicitly approved.

---

## Phase 0 — Baseline & Safety Rails (1–2 days)

### Tasks
1. Add a test harness (pytest) and a temporary DB fixture.
2. Add behavior snapshot tests for:
   - threshold calculation
   - proposal approval when budget sufficient
   - over-budget transition + later auto-approval
   - undo approval budget restoration
3. Add API auth tests for `X-Admin-Key` checks.

### Exit criteria
- CI (or local test command) runs green.
- Existing behavior is codified in tests.

---

## Phase 1 — Security Hardening (2–4 days)

### Tasks
1. Replace SHA-256 password storage with `werkzeug.security` (`generate_password_hash`, `check_password_hash`).
2. Introduce password migration path (legacy hashes accepted once and rehashed on login).
3. Remove hardcoded default admin password:
   - bootstrap admin via environment variable or one-time setup route.
4. Disable debug mode by default; drive via environment (`FLASK_DEBUG=false`).
5. Add CSRF protection for all form POST endpoints.
6. Add basic login/API rate limiting.
7. Tighten upload validation (MIME sniffing + extension allowlist + size limit).

### Exit criteria
- No plaintext/static default credentials.
- CSRF enforced on form writes.
- Security regression tests added.

---

## Phase 2 — Application Structure Refactor (3–5 days)

### Target structure
- `app/__init__.py` (app factory)
- `app/db.py` (connection lifecycle, schema helpers)
- `app/auth.py` (login/register/session guards)
- `app/proposals.py` (proposal CRUD + comments)
- `app/budget.py` (budget service + approval engine)
- `app/api.py` (REST endpoints)
- `app/notifications.py` (Telegram integration)

### Tasks
1. Move reusable logic into service functions:
   - `calculate_min_backers(...)`
   - `process_proposal(...)`
   - `recheck_over_budget(...)`
2. Eliminate duplicated threshold logic and shared SQL snippets.
3. Convert broad `except:` to targeted exceptions + logging.

### Exit criteria
- `app.py` replaced by thin entrypoint/app factory wiring.
- Core business logic callable without HTTP context.

---

## Phase 3 — Correctness Fixes (1–2 days)

### Tasks
1. Fix `trigger_monthly` to use `settings.monthly_topup` (not hardcoded 50).
2. Remove incorrect extra success flash in `add_budget` flow.
3. Validate numeric form input robustly (`Decimal`, bounds, error handling).
4. Restrict `/check-overbudget` (admin-only) or replace with scheduler job.
5. Add vote value validation (`in_favor|against`) at boundary.

### Exit criteria
- Known logic bugs resolved with tests.
- Admin actions behave as labeled.

---

## Phase 4 — Data & Query Optimization (2–3 days)

### Tasks
1. Reduce dashboard N+1 queries using aggregated joins/subqueries.
2. Add indexes:
   - `votes(proposal_id, vote)`
   - `proposals(status, created_at)`
   - `comments(proposal_id, created_at)`
3. Add transaction boundaries for budget mutations to reduce lock risk.

### Exit criteria
- Fewer queries per dashboard render.
- Stable behavior under concurrent voting/admin actions.

---

## Phase 5 — Operationalization (1–2 days)

### Tasks
1. Add structured logging and error reporting.
2. Add environment validation at startup (required keys, safe defaults).
3. Add backup/restore guidance for `hackerspace.db` and uploads.
4. Update docs:
   - `README.md` quick-start and env vars
   - migration notes for password hash transition

### Exit criteria
- App is easier to run safely in production.
- Refactor + migration steps documented.

---

## Test Strategy

- Unit tests for budget math and status transitions.
- Integration tests for key routes (login, vote, admin budget actions).
- API tests for auth and payload validation.
- Regression tests for every bug fixed in Phases 1–3.

Suggested commands:
- `pytest -q`
- `python -m py_compile app.py` (until entrypoint migration)

---

## Rollout Strategy

1. Ship in small PRs by phase and keep behavior-compatible by default.
2. Land tests first, then refactor behind tests.
3. Use feature flags for risky changes (auth migration, CSRF enforcement grace period).
4. Communicate user-impacting changes (admin bootstrap, stricter validation) in release notes.

---

## Risks & Mitigations

- **Risk:** Password migration locks users out.
  - **Mitigation:** dual-hash verify window + forced reset fallback.
- **Risk:** Refactor breaks approval semantics.
  - **Mitigation:** snapshot tests from Phase 0 + staged releases.
- **Risk:** CSRF rollout breaks existing forms.
  - **Mitigation:** add tokens across templates in one PR with integration tests.

---

## Definition of Done

- Security baseline met (no hardcoded admin secret, no unsalted hashes, debug off by default, CSRF on).
- Core budget/voting behavior covered by automated tests.
- Modular structure replaces monolithic business logic.
- Known correctness bugs fixed and regression tested.
- Documentation updated for operators and contributors.
