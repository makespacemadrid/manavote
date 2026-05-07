# Ideas for Improving This Codebase

This document captures concrete, incremental improvements identified during a detailed review.

## 1) Reliability / Startup

1. ✅ **Move app wiring out of `main_routes.py`** *(implemented)*
   - Flask app construction/config now lives in `app/web/app_setup.py`.
   - Follow-up opportunity: complete the split to blueprints so routes can be registered lazily per module.

2. **Avoid broad `except Exception` in startup paths**
   - Several startup operations swallow all exceptions and log warnings.
   - Prefer narrower exception classes and fail-fast for critical services.
   - Add startup health summary so misconfiguration is visible.

3. **Add explicit startup mode policy**
   - Document and enforce behavior matrix for `development`, `test`, `production`:
     - DB bootstrap behavior
     - scheduler behavior
     - debug mode
     - secret requirements

## 2) Security

4. **Replace static fallback bootstrap password with one-time random secret (non-prod only)**
   - Current non-production fallback is a fixed known string.
   - Better: generate random one-time secret at first boot, log once, require immediate change.

5. **Add audit logging for API calls**
   - Log endpoint, caller key fingerprint (not raw key), status, and latency.
   - Useful for abuse detection and incident analysis.

6. **Introduce API key rotation support**
   - Allow multiple valid keys temporarily (active + next), then revoke old key.
   - Simplifies safe credential rotation.

7. ✅ **Harden file upload validation** *(partially implemented)*
   - Replaced deprecated `imghdr` usage with explicit signature-based MIME sniffing for allowed image types.
   - Enforce max dimensions and content-type/extension agreement.

## 3) Data / Domain

8. **Add repository/service boundaries for API routes**
   - Some API endpoints still use direct SQL in route handlers.
   - Move DB logic into repositories/services for consistency and testability.

9. **Normalize statuses and transitions**
   - Centralize proposal lifecycle transitions in one state machine utility.
   - Validate illegal transitions early.

10. **Create DB indexes for common query paths**
    - Add indexes for proposal status/date filters and votes lookups.
    - Measure via `EXPLAIN QUERY PLAN` and benchmark before/after.

## 4) API Quality

11. **Add OpenAPI spec + schema validation**
    - Define endpoints and JSON schemas (`pydantic`/`marshmallow` or hand-rolled checks).
    - Auto-generate docs and request/response examples.

12. **Standardize error response format**
    - Return consistent shape, e.g. `{ "error": { "code": "...", "message": "..." } }`.
    - Helps clients implement stable error handling.

13. **Add list/search endpoint for proposals**
    - `GET /api/proposals?status=active&page=1&page_size=20`.
    - Useful for admin tooling and integrations.

## 4.1) Proposal voting channel refactor plan (Telegram / Web / Both)

14. **Introduce configurable proposal vote mode**
    - Add setting key: `proposal_vote_mode ∈ {web_only, telegram_only, both}`.
    - Admin UI control under Settings/Admin with clear help text and safe default (`both`).
    - Reuse current poll vote-mode UX patterns to minimize surprise.

15. **Unify proposal vote ingestion paths**
    - Define one service entrypoint (e.g., `VoteService.record_proposal_vote(source=web|telegram, ...)`) used by both `/vote/<id>` and Telegram webhook handlers.
    - Keep idempotency invariant: one member, one vote per proposal; repeated votes replace previous value.
    - Centralize validation + eligibility checks (proposal state, member mapping, option validity).

16. **Channel policy enforcement matrix**
    - `web_only`: accept web votes, reject Telegram votes with user-facing guidance.
    - `telegram_only`: reject web form submissions with flash message, accept Telegram commands/buttons.
    - `both`: accept either channel; latest vote wins.
    - Emit structured audit log per rejection/acceptance with channel + reason code.

17. **Telegram identity mapping hardening for proposal votes**
    - Reuse existing poll identity-linking behavior (`telegram_user_id` preferred, username fallback, placeholder strategy if needed).
    - Ensure unlinked users get deterministic guidance (`/link <app_username> <app_password>`).

18. **UI updates**
    - Dashboard/proposal detail should reflect current vote mode:
      - hide/disable web vote controls when not allowed,
      - show contextual banner when Telegram-only is active,
      - preserve counts/status visibility regardless of channel.

19. **Migration + backward compatibility**
    - Add migration to seed `proposal_vote_mode = both` when missing.
    - Preserve current behavior for existing deployments until admin changes setting.

20. **Test plan (frontend + backend)**
    - Unit: service-level policy checks for each mode/channel combination.
    - Functional: web route rejects/accepts by mode; Telegram webhook path rejects/accepts by mode.
    - Frontend: template assertions for hidden/disabled vote buttons + explanatory messages.
    - Regression: existing approval/budget transition logic remains unchanged across channels.

## 5) Internationalization (i18n)

21. ✅ **Add i18n completeness checks** *(implemented)*
    - Added tests to keep `en` and `es` keysets in sync.
    - Prevents silent translation drift during UI changes.

22. ✅ **Clean duplicated translation entries** *(implemented)*
    - Translation file has repeated keys and mixed casing patterns.
    - Normalize keys and enforce a style guide.

23. ✅ **Localize remaining hardcoded UI strings** *(implemented)*
    - Some new settings-related labels are still hardcoded in templates.
    - Move to translation keys to keep EN/ES coverage complete.

## 6) Testing

24. ✅ **Add dedicated integration test DB fixture** *(implemented)*
   - Current `APP_DB_PATH` session override is good; extend with transactional fixtures for isolation speed.

25. ✅ **Add production-mode configuration tests** *(implemented)*
   - Assert startup failures for missing `SECRET_KEY` and missing bootstrap password when `FLASK_ENV=production`.

26. **Add API contract tests**
   - Verify status codes, payload schema, and edge cases for all API endpoints.

27. **Add regression tests for import-time side effects**
   - Ensure importing modules does not mutate DB or schedule jobs unexpectedly.

## 7) Observability / Operations

28. **Structured logging**
   - JSON logs with request id/user id where available.

29. **Metrics endpoint / instrumentation**
   - Request latency, DB timings, error rates, proposal throughput.

30. **Backup validation job**
   - Periodically verify backups are readable and recent.

## 8) Developer Experience

31. **Pre-commit checks**
   - `ruff`/`black`/`isort` + simple static checks for translation keys.

32. **Architecture notes**
   - Add short ADRs for key decisions:
      - bootstrap strategy
      - API auth model
      - budget/committed calculation semantics

33. ✅ **Document environment variable matrix** *(implemented)*
   - One table showing defaults and behavior by environment (dev/test/prod).

34. ✅ **Extract shared navigation/settings partial** *(implemented)*
   - Navigation markup is duplicated across many templates.
   - Recent settings UX changes required touching many files and can introduce inconsistencies.
   - Create a shared Jinja partial/macro for top navigation to reduce churn and regressions.

35. ✅ **Template validation tests for malformed HTML snippets** *(implemented)*
   - Add lightweight checks that critical forms include complete CSRF input tags and valid key markup.
   - Helps catch accidental template breakage during repetitive find/replace edits.

36. **Reduce global state in `main_routes.py`**
   - `main_routes.py` still mixes many concerns (DB bootstrap, Telegram settings globals, template filters, API endpoints, admin actions).
   - Split into modules (`auth_routes.py`, `proposal_routes.py`, `poll_routes.py`, `admin_routes.py`) and shared services/helpers.
   - Benefit: lower import cost, easier ownership boundaries, simpler tests.

37. **Unify startup bootstrap path**
   - There are multiple startup steps spread across `app_setup`, `main_routes`, and `app.__init__.create_app()`.
   - Create a single explicit startup orchestration function that runs in a defined order (config → DB/migrations → services/scheduler).
   - Benefit: less surprise from import-time behavior and clearer lifecycle for tests/WSGI.

---

## Suggested priority order (next sprint)

1. **Proposal vote channel refactor (highest impact remaining)**
   - Add configurable **proposal** vote mode + policy enforcement (#14-#20)
   - Unify service ingestion for web/Telegram proposal votes (#15)
2. **Startup / architecture reliability**
   - Avoid broad `except Exception` in startup paths (#2)
   - Add explicit startup mode policy (#3)
   - Unify startup bootstrap path (#37)
3. **API/domain maintainability**
   - Add repository/service boundaries for API routes (#8)
   - Normalize statuses and transitions (#9)
4. **Operational visibility**
   - Structured logging (#28)
   - Metrics endpoint / instrumentation (#29)
5. **Structural cleanup**
   - app factory / blueprint split (#1)
   - Reduce global state in `main_routes.py` (#36)


## Next-sprint execution checklist (expanded from priority order)

### A) Proposal vote channel refactor (#14-#20)

- **Milestone A1 — data/config plumbing**
  - [x] Add `proposal_vote_mode` setting with allowed values `web_only|telegram_only|both` and default `both`. ✅ implemented
  - [x] Add migration/seed fallback for existing deployments where setting is absent. ✅ `run_migrations` now seeds `poll_vote_mode` and `proposal_vote_mode` defaults
  - [x] Add admin settings control (dropdown/radio) with i18n labels/help text. ✅ implemented (label/help i18n can be improved)

- **Milestone A2 — unified vote ingestion service**
  - [x] Introduce one service API for proposal votes, e.g. `record_proposal_vote(member_id, proposal_id, vote, source)`. ✅ implemented in routes layer; moved to dedicated service module (`app/services/proposal_vote_service.py`)
  - [x] Route both web form submissions and Telegram handlers through the same service. ✅ web and Telegram `/pvote` command/callback paths now share unified proposal vote ingestion
  - [x] Keep existing upsert behavior (latest vote wins per member/proposal). ✅ covered by existing functional poll/proposal vote replacement tests + centralized upsert path

- **Milestone A3 — policy enforcement + UX**
  - [x] Enforce mode matrix (`web_only`, `telegram_only`, `both`) in one policy helper. ✅ implemented via `can_record_proposal_vote(source)`
  - [x] Return clear user-facing messages when a channel is blocked. ✅ implemented for web routes
  - [x] Hide/disable web voting controls in Telegram-only mode and show explanatory banner. ✅ implemented on dashboard + proposal detail

- **Milestone A4 — tests and rollout safety**
  - [x] Unit tests for policy matrix by channel/mode. ✅ added `tests/test_proposal_vote_mode.py`
  - [x] Functional tests for web route behavior by mode. ✅ added for `telegram_only`, `web_only`, and `both` web paths
  - [x] Functional tests for Telegram webhook behavior by mode. ✅ covered for command/callback paths across `both`, `web_only`, and `telegram_only`
  - [x] Regression tests confirming vote upsert behavior is unchanged (latest vote wins per member/proposal). ✅ added functional test for proposal vote replacement

### B) Startup / architecture reliability (#2, #3, #37)

- **Milestone B1 — exception hardening**
  - [~] Replace broad startup exception handlers with targeted exceptions. *(in progress: app factory startup now narrows startup exception handling and fails fast on DB initialization errors)*
  - [ ] Fail fast for critical dependencies; log warnings only for optional integrations.

- **Milestone B2 — explicit startup policy**
  - [~] Implement a single environment-policy helper that validates required secrets/settings. *(in progress: `validate_startup_policy` added and wired into `app_setup` for production secret validation)*
  - [~] Enforce documented behavior for dev/test/prod before app starts serving requests. *(in progress: test environment now disables optional scheduler/auto-backup startup jobs via runtime policy helper)*

- **Milestone B3 — unified bootstrap orchestration**
  - [~] Create one orchestrator function for startup order: config → DB/migrations → scheduler/services. *(in progress: app factory now uses a single `_run_startup_steps` function for deterministic startup sequencing)*
  - [x] Move scattered bootstrap steps into that orchestrator and call it from app factory. ✅ `create_app()` now delegates startup sequence to startup orchestration helper (`run_startup_steps` in `app/startup.py`)

- **Milestone B4 — startup regression tests**
  - [x] Add tests for deterministic startup order. ✅ covered in `tests/test_app_startup.py`
  - [x] Add tests for optional-startup warning behavior (`ImportError`, scheduler/backup warnings). ✅ covered in `tests/test_app_startup.py`

### C) API/domain maintainability (#8, #9)

- **Milestone C1 — API boundary cleanup**
  - [ ] Move remaining direct SQL out of API route handlers into repositories/services.
  - [ ] Keep route handlers thin: parse/validate request, call service, format response.

- **Milestone C2 — transition integrity**
  - [ ] Create central proposal state-transition helper.
  - [ ] Reject illegal transitions with deterministic error codes/messages.

### D) Ops visibility (#28, #29)

- **Milestone D1 — structured logs**
  - [ ] Add JSON logging mode with request id, actor id, endpoint, status, latency.
  - [ ] Add API key fingerprint (never raw key) for admin/API operations.

- **Milestone D2 — metrics**
  - [ ] Add basic instrumentation for request latency, error rate, and DB timings.
  - [ ] Expose `/metrics` (or equivalent) behind admin/internal network controls.


## Sprint review (current)

### Completed this sprint
- Implemented configurable `proposal_vote_mode` with service-level normalization/policy helpers.
- Centralized proposal vote ingestion and preserved upsert semantics (latest vote wins).
- Added admin control + UI behavior for Telegram-only mode (control hiding + user banner).
- Added policy matrix tests (unit + functional), plus full-suite stability hardening.

### Remaining high-priority items
- Wire Telegram **proposal** vote ingestion into shared proposal vote service path. ✅ implemented via `/pvote <proposal_id> <yes|no>` command path
- Add functional webhook tests for proposal vote behavior by mode (`web_only`, `telegram_only`, `both`). ✅ added for `both` and `web_only`; `telegram_only` functional mode test now added; plus bot-suffix, unknown-member, and callback-query regression checks
- Add channel-level audit logging for accepted/rejected proposal votes with reason codes. ✅ implemented (`proposal_vote_accepted` / `proposal_vote_rejected`)


## Focused review notes (May 6, 2026)

After another pass through routes/services/tests, these are the most actionable near-term improvements:

1. **Extract Telegram webhook handling from `main_routes.py` into a dedicated adapter module**
   - Keep webhook parsing + command dispatch in `app/integrations/telegram_*` and leave HTTP concerns in routes only.
   - This will reduce route complexity and make message-flow tests cheaper to maintain.
   - ✅ progress: extracted payload parsing, command classification, and callback/proposal/poll/link response text mapping into `app/integrations/telegram_webhook.py`, and updated route to consume normalized webhook adapter helpers.

2. **Add a single proposal-vote event schema for logs**
   - The accepted/rejected proposal vote logs exist; standardize the payload keys (`event`, `source`, `mode`, `proposal_id`, `member_id`, `reason_code`, `latency_ms`) so dashboards/alerts can be added without refactors.
   - ✅ progress: proposal vote logs now use a shared helper with consistent key order (`event/source/mode/proposal_id/member_id/vote/reason_code/latency_ms`).

3. **Harden settings reads with typed accessors**
   - Add typed helpers for enum-like settings (for example vote modes) that validate and normalize once, then cache per request.
   - Prevents drift where separate call sites implement slightly different fallback behavior.
   - ✅ progress: added shared enum-setting helper and switched poll/proposal vote mode lookups to common normalization path.

4. **Introduce repository contract tests for proposal/vote repos**
   - Add a compact reusable suite that runs against SQLite test DB and verifies upsert/idempotency invariants directly at repository level.
   - This will protect service refactors and speed root-cause isolation when behavior changes.
   - ✅ progress: added vote repository contract tests for upsert replacement and count invariants.

5. **Add smoke tests for app-factory startup order**
   - Assert `create_app()` startup sequence (config validation → migrations → route registration) under dev/test/prod settings.
   - Prevent regressions from import-time side effects while bootstrap continues to be refactored.

---

## Next sprint plan (May 2026)

### Sprint goal
- **Stabilize startup policy + reduce `main_routes.py` coupling** while preserving current proposal-vote behavior and test coverage.

### Planned deliverables

1. **Startup policy helper (B2)**
   - Add a dedicated helper (for example `app/startup_policy.py`) that validates environment-specific requirements before app serving:
     - `production`: enforce non-default `SECRET_KEY` and bootstrap-password policy,
     - `test`: deterministic defaults with no scheduler side effects,
     - `development`: permissive defaults with explicit warnings.
   - Wire helper into `create_app()` so policy checks run before startup orchestration.

2. **Finish startup orchestration extraction (B3)**
   - Move remaining startup-adjacent behavior out of route module globals where feasible.
   - Keep `_run_startup_steps` as the single sequencing entrypoint and tighten function boundaries (inputs/outputs only, no hidden globals).

3. **Telegram webhook adapter split (Focused note #1)**
   - [x] Extract webhook parsing/dispatch from `main_routes.py` into `app/integrations/telegram_webhook.py`. ✅ route command/callback dispatch now flows through `dispatch_message` / `dispatch_callback` helpers.
   - [x] Route handler should become a thin HTTP adapter: parse request → call integration service → map result to response. ✅ `telegram_webhook` now delegates branching to integration helpers and only performs transport side-effects.

4. **Proposal-vote audit schema normalization (Focused note #2)**
   - [x] Standardize structured log payload keys for accepted/rejected proposal votes: `event, source, mode, proposal_id, member_id, reason_code, latency_ms`.
   - [x] Add regression tests asserting log event names and required fields.

5. **Repository contract test scaffolding (Focused note #4)**
   - Add reusable test mixins/helpers for proposal/vote repository invariants:
     - one member/one vote semantics,
     - upsert replacement behavior,
     - deterministic reads after writes.

### Test plan for the sprint
- Extend startup tests with mode-specific policy assertions (`dev/test/prod`) and import-side-effect guards.
- Add webhook-adapter functional tests for command + callback parity.
- Add audit-log assertion tests for proposal vote acceptance/rejection.
- Keep `tests/test_production_config.py` and `tests/test_app_startup.py` green as gating checks.

### Exit criteria
- `create_app()` uses explicit policy validation + startup orchestration with no broad startup exception swallowing.
- Telegram webhook route no longer contains business-flow branching beyond HTTP adaptation.
- Proposal-vote logs have one documented schema used consistently across accepted/rejected paths.
- New tests land with clear coverage of startup policy, webhook adapter behavior, and repository vote invariants.


## Active backlog (post-implementation cleanup)

The following are the items that are still pending after the recent startup, webhook, vote-mode, and test hardening work.

### Highest priority
- Finish startup policy matrix enforcement for all environments (dev/test/prod) with explicit validations beyond `SECRET_KEY`. *(in progress: production secure-cookie enforcement added)*
- Continue extracting Telegram webhook command dispatch from `main_routes.py` into dedicated integration handlers (payload parsing + response mapping is already extracted).
  - ✅ completed: webhook command and callback dispatch are centralized in `app/integrations/telegram_webhook.py`; route now acts as HTTP adapter.
- Expand repository contract tests from vote repository to proposal + settings repositories.

### Next priority
- Add API contract tests with stable error-schema assertions.
- Add structured JSON logging mode and request-level correlation fields.
- Complete route boundary cleanup by reducing direct SQL in remaining API/admin handlers.

### Done recently (for context only; not backlog)
- Deterministic startup orchestration (`run_startup_steps`) and startup policy helper scaffolding.
- Startup reliability tests (`test_app_startup`, `test_startup_policy`) including fail-fast/warning boundaries.
- Shared enum settings normalization helper + vote mode normalization usage.
- Proposal vote audit event normalization including latency field.
- Telegram webhook payload/response helper extraction for callback, proposal vote, poll vote, and link responses.
- Vote repository upsert/count contract tests and route-level proposal vote write via repository.
