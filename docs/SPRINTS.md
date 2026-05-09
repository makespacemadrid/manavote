# SPRINTS — Implementation Planning and Progress Tracking

Last updated: 2026-05-09

This document contains execution planning, sprint scope, in-flight tracking, and completion status.

## How to use this document

- Keep this file focused on implementation sequencing, completion logs, and remaining execution tasks.
- Record only actionable progress entries here (do not duplicate backlog/spec prose from `IDEAS.md`).
- When sprint scope changes, update:
  1. the sprint scope section,
  2. progress log entries,
  3. remaining-work checklist.

## Current implementation focus (Q2 2026)

- Complete MCP parity with REST for admin automation (read + create + validation parity).
- Stabilize docs so README remains concise and `docs/*` are the authoritative detail source.
- Finish `main_routes.py` decomposition with measurable completion criteria and cleanup milestones.

## 7) Sprint Plan Continuation

### Sprint 1 (Completed)
1. **Route decomposition kickoff**
   - Status: **In progress**
   - Extracted startup and configuration concerns into dedicated modules; route-layer split remains the primary carry-over.
2. **Startup orchestration baseline**
   - Status: **Completed (baseline)**
   - Deterministic startup checks and production policy tests are in place; next increment is structured startup reporting.
3. **API consistency baseline**
   - Status: **In progress**
   - Core API hardening has begun, but standardized error envelopes and contract coverage are not yet uniform.

### Sprint 2 (Completed)

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
- ✅ Extracted shared route helpers (timezone/datetime, username normalization, image type detection) into `app/web/routes/helpers/main_helpers.py` and removed duplicated compatibility helper code from `main_routes.py`.
- ✅ Added helper-focused regression tests for `main_helpers` to lock formatting and file-type detection behavior during ongoing route decomposition.
- ✅ Migrated `/polls` handler implementation out of `main_routes.py` into `poll_routes.py` (no longer delegation-only wrapper).
- ✅ Migrated `/check-overbudget` handler implementation out of `main_routes.py` into `admin_routes.py` (compatibility shim retained).
- ✅ Migrated `/telegram-settings` handler implementation out of `main_routes.py` into `auth_routes.py` (compatibility shim retained).
- ✅ Migrated `/admin/backups/<backup_type>/<filename>` download handler out of `main_routes.py` into `admin_routes.py` (compatibility shim retained).
- ✅ Migrated `/settings` handler implementation out of `main_routes.py` into `auth_routes.py` (compatibility shim retained).
- ✅ Migrated `/register` handler implementation out of `main_routes.py` into `auth_routes.py` (compatibility shim retained).
- ✅ Migrated `/` landing handler implementation out of `main_routes.py` into `auth_routes.py` (compatibility shim retained).
- ✅ Migrated `/healthz` handler implementation out of `main_routes.py` into `auth_routes.py` (compatibility shim retained).
- ✅ Migrated `/about` handler implementation out of `main_routes.py` into `proposal_routes.py` (compatibility shim retained).
- ✅ Migrated `/calendar` handler implementation out of `main_routes.py` into `proposal_routes.py` (compatibility shim retained).
- ✅ Expanded blueprint endpoint-alias regression tests to cover newly migrated root/health/about/calendar/settings/register endpoints.

### Sprint 2 Exit Criteria (Status)
- `main_routes.py` net line count reduced meaningfully with no feature regressions.
- Startup emits a single machine-readable summary event on every boot.
- Target API endpoints return uniform error envelopes under all tested failure paths.
 - **Status:** ✅ Completed.

This scope remains intentionally narrow to preserve delivery focus while unblocking WS-A/WS-B/WS-C in parallel.

## Sprint 3 (In Progress) — MCP + Docs Consolidation

### Goals
1. Ensure MCP tools cover key admin automation flows, including POST-like create actions.
2. Align MCP validation with REST/business rules where behavior should match.
3. Keep authoritative documentation synchronized across `APIDOC`, `SPEC`, `TESTING`, and the docs index.

### Delivered so far
- ✅ Added MCP create tools: `create_member`, `create_proposal`, `create_poll`.
- ✅ Added MCP tests for create flows and key validation rejection paths.
- ✅ Added `docs/INDEX.md` and split testing guidance into `docs/TESTING.md`.
- ✅ Expanded `SPEC.md` with explicit MCP tool surface and codebase map.
- ✅ Documented MCP error-code conventions in APIDOC and added explicit MCP create-request example payload.
- ✅ Added additional MCP negative-path tests (duplicate username, missing creator, invalid poll option length).
- ✅ Added explicit MCP error-code contract regression test covering validation (`-32602`), conflict (`-32010`), and not-found (`-32004`) classes.
- ✅ Added API/MCP sprint changelog snippet to APIDOC for recent behavior/documentation updates.
- ✅ Expanded MCP negative-path checks across create tools (including proposal non-positive amount and poll missing-creator not-found path).
- ✅ Added MCP tool-discovery regression coverage to ensure create tools remain advertised via `tools/list`.

### Remaining work (execution checklist)
1. **MCP parity hardening**
   - Add remaining parity checks where REST and MCP should enforce the same limits/messages.

2. **Contract consistency**
   - Expand error-code contract tests across more MCP tools as new tool classes are added.

3. **Docs quality pass**
   - Keep sprint changelog snippet in APIDOC updated when MCP/REST contracts change.

### Exit criteria
- MCP create tools have both happy-path and key negative-path coverage.
- APIDOC and SPEC reflect the same MCP tool set and argument constraints.
- README remains concise and links only to canonical docs for deep detail.

## Proposed Sprint 4 Scope (Preview)
- Remove transitional endpoint aliases once templates and callers fully use blueprint-native endpoint names.
- Finalize service/repository boundaries for remaining admin/proposal write paths.
- Add broader API contract matrix tests (happy path + key rejection paths) for core REST endpoints.
