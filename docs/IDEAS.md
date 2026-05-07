# IDEAS — Product & Engineering Improvement Plan

Last updated: 2026-05-07

This document is a living plan for improving maintainability, reliability, product clarity, and operational confidence.
It is intentionally practical: each section defines outcomes, concrete initiatives, and measurable exit criteria.

---

## 0) Planning Principles

- **Stability first:** startup, data integrity, and policy enforcement are prioritized before feature expansion.
- **Single source of truth:** business rules belong in services/policies, not duplicated across routes/templates/integrations.
- **Observable by default:** every critical path should emit structured logs and testable outcomes.
- **Incremental migration:** prefer compatible refactors over big-bang rewrites.

---

## 1) Current State (Executive Snapshot)

### Strengths
- App setup responsibilities have started moving out of route files into dedicated setup modules.
- Proposal vote-mode support (`web_only` / `telegram_only` / `both`) exists with service-level handling.
- Production/startup behavior has regression coverage in tests.
- i18n key parity and template guard checks reduce UI regressions.

### Gaps
- `main_routes.py` still carries too many concerns (routing + orchestration + integration glue).
- Startup behavior is spread across multiple import/runtime paths.
- API contracts are inconsistent (error shape and validation vary by endpoint).
- Observability is limited (mostly plain logs, sparse metrics).

---

## 2) Strategic Outcomes (Next Quarter)

1. **Route layer becomes thin and modular** (Blueprint-oriented, low coupling).
2. **Startup is deterministic and auditable** (single orchestrator + explicit checks).
3. **API behavior is contract-driven** (stable schemas + standardized errors).
4. **Operations are diagnosable** (structured events, key counters, backup confidence).

---

## 3) Workstreams & Backlog

## WS-A — Architecture Refactor (P0)

### A1. Decompose `main_routes.py`
**Goal:** reduce mixed concerns and improve ownership/testability.

- Split into:
  - `auth_routes.py`
  - `proposal_routes.py`
  - `poll_routes.py`
  - `admin_routes.py`
  - `api_routes.py`
- Move shared helper logic into `app/web/routes/helpers/` or service layer.
- Register all route modules through blueprints in app setup.

**Done when**
- `main_routes.py` is either removed or reduced to a compatibility shim.
- Route modules have focused tests and minimal cross-imports.

### A2. Service/repository boundary completion
**Goal:** remove direct SQL from route handlers.

- Route handlers call service methods only.
- Repositories own query concerns.
- Domain operations use explicit service entrypoints.

**Done when**
- No write SQL exists in route handlers.
- Critical operations (proposal updates/votes/admin actions) have service-level unit coverage.

---

## WS-B — Startup Reliability (P0)

### B1. Single startup orchestrator
**Goal:** one explicit startup lifecycle.

Proposed order:
1. config load + validation
2. DB connect + migrations
3. settings/bootstrap checks
4. integrations (Telegram, scheduler)
5. readiness summary

### B2. Exception policy and startup report
- Replace broad catch-all behavior with targeted exception classes.
- Define severity:
  - **fatal:** must stop app start
  - **degraded:** app may start but must emit warning with reason code
- Emit one structured startup summary event.

**Done when**
- Startup behavior is deterministic across dev/test/prod.
- Failures are visible and actionable without reading stack traces deeply.

---

## WS-C — API & Domain Consistency (P1)

### C1. Standard error envelope
Adopt a uniform format for all API failures:

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "human-readable message"
  }
}
```

### C2. Request/response schema checks
- Define endpoint schemas.
- Validate incoming payloads and guarantee response shape.

### C3. Proposal lifecycle state machine
- Centralize allowed transitions.
- Reject illegal transitions with stable error codes.

### C4. Query/index review
- Add indexes for high-frequency filters/lookups.
- Record before/after query plans for key endpoints.

**Done when**
- API contract tests cover every endpoint path (success + failure).
- Proposal transition errors are deterministic and documented.

---

## WS-D — Security & Operations (P2)

### D1. Credential hardening
- Replace non-prod static bootstrap fallback with one-time generated secret flow.
- Add safe API key rotation window (`active` + `next`).

### D2. Structured logs and telemetry
- JSON log fields: request_id, actor_id, endpoint, status, latency_ms, reason_code.
- Add counters/timers for vote throughput, error rates, and request latency.

### D3. Backup validation
- Periodic job verifies backup recency and readability.
- Emit health signal when RPO threshold is exceeded.

**Done when**
- Audit/debug workflows are possible from logs + metrics without manual DB inspection.

---

## 4) Proposal Voting — Forward Outlook

The vote-mode refactor is functionally in place; focus now shifts to consistency, clarity, and telemetry.

### Product polish
- Keep blocked-channel guidance consistent across dashboard, proposal detail, and Telegram responses.
- Show admins an “effective vote policy” summary with current mode and implications.

### Safety/operations
- Track accept/reject counts by source and reason code.
- Add migration sanity tests for seeded defaults in both fresh and existing deployments.

### UX quality gates
- If `telegram_only`, web voting controls must always be hidden/disabled with explanatory text.
- If `web_only`, Telegram responses must provide clear next-step guidance.

---

## 5) 30 / 60 / 90 Day Delivery Plan

### 30 Days (Foundation)
- Blueprint scaffolding + initial route split.
- Startup orchestrator introduced behind parity tests.
- API error envelope standardized on existing endpoints.

### 60 Days (Consolidation)
- Service/repository boundary complete for highest-traffic paths.
- Proposal state machine integrated in write flows.
- Structured logging fields available in all HTTP/API handlers.

### 90 Days (Confidence)
- Full API contract test coverage.
- Metrics + backup validation job running.
- `main_routes.py` retired or minimized.

---

## 6) Definition of Done (Applies to All New Work)

A change is complete only when:
- Business behavior is enforced in services/policies (not route-only).
- Tests cover expected success and rejection paths.
- Logs/events include stable machine-readable fields.
- Migration/config impacts are documented.
- User-visible behavior changes are reflected in i18n and templates.

---

## 7) Sprint Plan Continuation

### Sprint 1 (Completed / In Progress)
1. **Route decomposition kickoff**
   - Status: **In progress**
   - Extracted startup and configuration concerns into dedicated modules; route-layer split remains the primary carry-over.
2. **Startup orchestration baseline**
   - Status: **Completed (baseline)**
   - Deterministic startup checks and production policy tests are in place; next increment is structured startup reporting.
3. **API consistency baseline**
   - Status: **In progress**
   - Core API hardening has begun, but standardized error envelopes and contract coverage are not yet uniform.

### Sprint 2 (Recommended Scope)

1. **Finish first blueprint extraction slice (auth + proposals)**
   - Move handlers and helper code out of `main_routes.py`.
   - Keep backward-compatible endpoint behavior and template rendering.
   - Add focused tests per extracted module.

2. **Introduce startup summary event with reason codes**
   - Emit one structured startup log summary containing:
     - startup mode (`dev`/`test`/`production`)
     - readiness status (`ready`/`degraded`/`failed`)
     - degraded reason codes (if any)
   - Ensure degraded vs fatal paths are explicitly test-covered.

3. **Standardize error envelope on top-priority API endpoints**
   - Apply common `{"error": {"code", "message"}}` response shape to:
     - `POST /api/register`
     - `POST /api/proposals`
     - `GET /api/proposals/<proposal_id>`
   - Add contract tests that assert both status code and envelope structure.

### Sprint 2 Progress Log
- ✅ First safe slice started: introduced blueprint modules (`auth_routes.py`, `api_routes.py`, `proposal_routes.py`, `poll_routes.py`, `admin_routes.py`) and centralized blueprint registration in `app/web/routes/__init__.py`.
- ✅ Migrated **auth + api route registration** off direct `@app.route` decorators in `main_routes.py` and into dedicated blueprint modules while preserving existing handler logic.
- ✅ Second safe slice started: proposal/poll/admin route registration moved into dedicated blueprints (`proposal_routes.py`, `poll_routes.py`, `admin_routes.py`).
- ✅ Auth handler implementations moved out of `main_routes.py` into `auth_routes.py` (no longer just delegation wrappers).
- ✅ API handler implementations moved from `main_routes.py` into `api_routes.py` with local request/auth/validation helpers.
- ✅ Added regression guard for legacy endpoint aliases so `url_for(...)` compatibility remains protected during route extraction.
- ✅ Legacy endpoint compatibility now covers URL building (`url_for`) via URL-map alias registration, not only `view_functions` lookup aliases.
- ✅ Blueprint registration made idempotent to prevent duplicate-registration failures when `create_app()` is invoked multiple times in tests/runtime utilities.
- ✅ Extracted shared API request/auth/validation helpers into `app/web/routes/helpers/api_helpers.py` and rewired `api_routes.py` to consume them.
- ✅ Added helper-focused tests for shared API route helpers to lock in request/auth/validation behavior during extraction.
- 🔜 Next slice: extract shared helpers into `app/web/routes/helpers/` and continue removing compatibility code from `main_routes.py`.

### Sprint 2 Exit Criteria
- `main_routes.py` net line count reduced meaningfully with no feature regressions.
- Startup emits a single machine-readable summary event on every boot.
- Target API endpoints return uniform error envelopes under all tested failure paths.

This scope remains intentionally narrow to preserve delivery focus while unblocking WS-A/WS-B/WS-C in parallel.

### Sprint 2 Remaining Work (Execution Checklist)

1. **Route extraction completion pass**
   - Move remaining web/admin/poll handler implementations out of `main_routes.py` into:
     - `proposal_routes.py`
     - `poll_routes.py`
     - `admin_routes.py`
   - Keep `main_routes.py` as compatibility-only surface (shared utilities + transitional imports).

2. **Error-envelope normalization pass (API-first)**
   - Introduce a small helper for standard API errors:
     ```json
     {
       "error": {
         "code": "stable_machine_code",
         "message": "human-readable message"
       }
     }
     ```
   - Apply this envelope first to:
     - `POST /api/register`
     - `POST /api/proposals`
     - `GET /api/proposals/<proposal_id>`

3. **Contract + compatibility test pass**
   - Extend tests to cover:
     - error envelope shape for selected endpoints,
     - blueprint endpoint alias compatibility,
     - helper-level validation edge-cases.
   - Keep one focused decomposition test command in `QUICKSTART.md` synchronized with newly added tests.

4. **Startup observability baseline**
   - Emit one structured startup summary log event with:
     - environment,
     - readiness status,
     - degraded reason codes (if any).
   - Add minimal assertions in startup tests to prevent silent regressions.

### Proposed Sprint 3 Scope (Preview)
- Remove transitional endpoint aliasing once all call sites/templates use blueprint-native endpoint names.
- Finalize service/repository boundaries for admin and proposal write paths.
- Add API contract matrix tests (happy-path + all key rejection paths) for core endpoints.
