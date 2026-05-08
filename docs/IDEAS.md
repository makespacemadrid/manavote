# IDEAS — Product & Engineering Improvement Plan

Last updated: 2026-05-08

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

### Forward outlook (next increments after recent admin UX updates)

Recent changes improved operational clarity in the admin/user UI:
- Admin can now unlink member Telegram identities without manual DB edits.
- Admin backup lists now expose direct download actions for DB/image backup artifacts.
- Vote policy and `/link` onboarding copy are clearer in settings and polls touch points.

Next high-impact increments should focus on finishing the reliability loop behind those UI controls:

1. **Backup downloads: add explicit audit trail + ownership metadata**
   - Log download events with `actor_id`, file type, file name, and timestamp.
   - Show backup creation source (`manual` vs `scheduled`) and age buckets in admin UI.
   - Exit criteria: admins can answer “who downloaded what and when” from logs alone.

2. **Telegram link lifecycle hardening**
   - Add explicit “last linked at” and “linked by telegram_user_id” metadata.
   - Add optional self-service unlink for members (with confirmation + warning copy).
   - Exit criteria: support/admin can resolve link issues without ad-hoc SQL inspection.

3. **Vote policy observability from config to behavior**
   - Emit reason-coded events when votes are blocked due to mode (`web_only`/`telegram_only`).
   - Add a compact “policy effect” test matrix across dashboard, proposal detail, polls, and Telegram webhook responses.
   - Exit criteria: every blocked vote path has both user-facing guidance and machine-readable reason codes.

### UX / UI design plan (product-design execution track)

This plan frames front-end improvements the way a UI/UX design team would: user journeys first, then information architecture, interaction patterns, and measurable outcomes.

#### A) UX foundations: personas, journeys, and task-critical flows
- Define primary personas:
  - **Member (casual):** votes occasionally, needs quick clarity and low friction.
  - **Member (power):** votes frequently, comments, tracks proposal status.
  - **Admin/operator:** manages policy, backups, Telegram integration, moderation.
- Map top journeys (current-state → target-state):
  1. First login → understand how to vote and where.
  2. Link Telegram → confirm success → recover from errors.
  3. Vote on poll/proposal under each vote mode (`both`, `web_only`, `telegram_only`).
  4. Admin weekly maintenance (backup, policy checks, member management).
- Deliverables:
  - Journey maps with friction points.
  - Prioritized UX debt list by severity (blocker/high/medium/low).

#### B) Information architecture and navigation coherence
- Create a unified IA pass for:
  - Top nav labels/order.
  - Settings vs Admin boundaries.
  - “Where do I do this?” discoverability for Telegram, voting policy, and backups.
- Add a consistent page-level “context header” pattern:
  - title
  - one-line purpose
  - primary action
  - secondary help link
- Exit criteria:
  - First-time users can locate Telegram linking and voting policy in ≤2 clicks.

#### C) Visual system and component consistency
- Establish a lightweight design system in code:
  - semantic color tokens (success/warning/error/info/background/surface)
  - spacing scale (4/8/12/16/24/32)
  - typography scale for headings/body/meta text
  - consistent button hierarchy (`primary`, `secondary`, `danger`, `ghost`)
- Normalize reusable components:
  - Alert/banner
  - Empty state
  - Status badge
  - Data table with actions
  - Confirmation modal pattern
- Exit criteria:
  - UI consistency audit score improves and repeated inline styles are reduced meaningfully.

#### D) Form UX and microcopy quality
- Apply form standards to admin and member forms:
  - clear labels and helper text
  - inline validation messages near fields
  - actionable error copy (“what happened + what to do next”)
  - disabled-state rationale when actions are unavailable
- Rewrite critical microcopy with a style guide:
  - concise, directive, non-ambiguous language
  - avoid internal jargon
  - include next step for every warning/error state
- Exit criteria:
  - Reduction in repeated support questions around linking/voting mode behavior.

#### E) Accessibility and responsive quality gates
- Accessibility baseline:
  - keyboard navigability for all controls
  - visible focus states
  - sufficient color contrast
  - semantic landmarks/headings
  - ARIA labels for icon-only controls
- Responsive baseline:
  - mobile-first checks for nav, tables, and multi-action admin rows
  - preserve tap target size and spacing for destructive actions
- Exit criteria:
  - Pass internal accessibility checklist + no critical mobile usability regressions.

#### F) Trust and safety UX for operational actions
- Add explicit risk cues for destructive/admin actions:
  - unlink Telegram
  - remove member
  - delete poll
- Introduce richer confirmation dialogs:
  - explain impact
  - require explicit confirmation for high-risk operations
  - show post-action success state with undo guidance (where feasible)
- Exit criteria:
  - Fewer accidental destructive actions; clearer recovery path when mistakes occur.

#### G) Measurement and experimentation
- Define product UX metrics:
  - Telegram link completion rate
  - Vote completion rate by channel
  - Drop-off at vote attempts blocked by policy
  - Time-to-success for admin backup download flow
- Add low-overhead instrumentation events for critical UI actions.
- Use small A/B or staged rollout for copy/layout changes where risk exists.
- Exit criteria:
  - Dashboard of baseline vs post-change metrics for each major UX initiative.

#### H) Delivery sequence (design-to-build pipeline)
1. **Discovery sprint (1–2 weeks):** journey maps, UX debt audit, IA proposals.
2. **Design sprint (1–2 weeks):** wireframes + component standards + copy pass.
3. **Implementation sprint A:** high-impact flows (Telegram linking, vote mode clarity, admin backup actions).
4. **Implementation sprint B:** component refactor + accessibility/responsive cleanup.
5. **Validation sprint:** usability test pass + metric review + backlog reprioritization.

#### I) Prioritization matrix (what ships first)

Use this rubric to sequence front-end items:
- **Impact (0–3):** user value + risk reduction.
- **Confidence (0–3):** confidence in solution based on evidence/tests.
- **Effort (1–3):** implementation cost (lower is better).
- **Score:** `(Impact + Confidence) / Effort`.

Initial priority candidates:
1. Telegram linking clarity across all entry points (high impact, low effort).
2. Vote-mode blocked-state consistency (high impact, medium effort).
3. Admin destructive action confirmations (medium impact, low effort).
4. Design token/component consolidation (high long-term value, medium effort).
5. Accessibility/focus-state cleanup (high impact, medium effort).

#### J) UX acceptance criteria template (for every new UI change)

Every UI task in the backlog should define:
1. **User story:** “As a ___, I want ___ so that ___.”
2. **Primary success path:** exact steps and expected result.
3. **Failure/edge paths:** at least 2 (validation + permission/policy case).
4. **Copy requirements:** exact message content for success/warning/error.
5. **Instrumentation event(s):** event name + core payload fields.
6. **Test coverage:** at minimum one template/assertion + one route/service behavior check.

#### K) Design QA and release checklist

Before release of UX-impacting changes:
- Run visual QA on desktop + mobile breakpoints (small/medium/large).
- Verify keyboard-only navigation for touched pages.
- Verify color contrast and focus indicators on changed controls.
- Confirm empty/loading/error states are present and readable.
- Confirm analytics events fire for critical actions.
- Capture before/after screenshots for major layout or interaction changes.
- Add a short changelog note explaining user-facing behavior updates.

#### L) Front-end implementation backlog (ready-to-build epics)

Translate the UX plan into concrete engineering epics with Definition of Done:

**Epic FE-1: Navigation + page-context standardization**
- Scope:
  - Introduce shared “page context header” partial/component.
  - Normalize top-nav order and naming across member/admin pages.
  - Add inline “where am I / what can I do here” helper copy in key pages.
- DoD:
  - Applied on Dashboard, Polls, Settings, Admin.
  - No endpoint or permission regressions.
  - Template guard tests updated for new shared partial.

**Epic FE-2: Telegram linking UX end-to-end**
- Scope:
  - Consolidate `/link` guidance into one reusable alert component.
  - Add explicit link-state badges (Linked / Not linked / Needs relink).
  - Add clearer error-recovery copy for invalid credentials or already-linked Telegram ID.
- DoD:
  - Guidance is consistent in Polls, Telegram Settings, and any Telegram-only vote blocks.
  - Tests assert presence of state badge + command hint in all relevant pages.

**Epic FE-3: Vote policy visibility and blocked-state consistency**
- Scope:
  - Standardize blocked voting banners for `web_only` and `telegram_only`.
  - Add a compact “Why this is disabled” component reused by poll/proposal views.
  - Ensure admin “effective vote policy” card and user-facing behavior stay aligned.
- DoD:
  - Shared component used in at least proposal detail + polls.
  - Contract tests verify copy and behavior under each vote mode.

**Epic FE-4: Admin operations safety UX**
- Scope:
  - Replace basic browser confirms with standardized confirm modal for destructive actions.
  - Include impact summary for unlink/remove/delete actions.
  - Add post-action success toasts/messages with next-step hints.
- DoD:
  - Destructive actions require explicit confirmation language.
  - UI copy reviewed for clarity and consistency.
  - Tests cover action availability and confirmation trigger wiring.

**Epic FE-5: Backup center UX (admin)**
- Scope:
  - Turn backup list into richer table (type, created at, size, source, actions).
  - Add filter/tabs for DB vs image backups.
  - Show validation-friendly errors and empty states.
- DoD:
  - Download links, empty states, and error states are deterministic and tested.
  - Backup rows are readable on mobile breakpoints.

#### M) Quarterly UX milestones with measurable checkpoints

**Milestone M1 (Weeks 1–3): Clarity baseline**
- Target outcomes:
  - Users find Telegram linking instructions quickly.
  - Vote-mode disabled states are understandable.
- Checkpoints:
  - FE-1 and FE-2 complete.
  - Link-related support questions trend down release-over-release.

**Milestone M2 (Weeks 4–7): Safety + consistency**
- Target outcomes:
  - Destructive admin actions have lower mistake rates.
  - Shared UI patterns reduce copy/style drift.
- Checkpoints:
  - FE-3 and FE-4 complete.
  - Confirm-dialog and blocked-state patterns fully standardized.

**Milestone M3 (Weeks 8–12): Operational confidence**
- Target outcomes:
  - Backup workflows are fast and low-error.
  - UX analytics can explain user drop-off points.
- Checkpoints:
  - FE-5 complete.
  - UX event dashboard reviewed in sprint retro and informs next roadmap cycle.

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
- ✅ Blueprint registration made idempotent to prevent duplicate-registration failures when `create_app()` is invoked multiple times in tests/runtime utilities.
- ✅ Extracted shared API request/auth/validation helpers into `app/web/routes/helpers/api_helpers.py` and rewired `api_routes.py` to consume them.
- ✅ Added helper-focused tests for shared API route helpers to lock in request/auth/validation behavior during extraction.
- ✅ Added startup summary event logging (`mode`, `status`, `degraded_reasons`) plus regression tests for ready/degraded outcomes.
- ✅ Standardized API error envelope (`{"error": {"code", "message"}}`) for `POST /api/register`, `POST /api/proposals`, and `GET /api/proposals/<proposal_id>` with contract tests.
- ✅ Added regression coverage for new admin operations: Telegram unlink action and backup download endpoint validation/serving behavior.
- ✅ Added reusable Telegram link-status template partial to reduce duplicated UI markup across member touch points.
- ✅ Upgraded admin backup UX from flat lists to structured tables (type/file/size/created/action) to improve operator scanability.
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
