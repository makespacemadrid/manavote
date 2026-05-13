# SPRINTS — Implementation Planning and Progress Tracking

Last updated: 2026-05-13

This document tracks implementation sequencing, active sprint scope, and completion status.
Backlog strategy and long-range direction live in [`IDEAS.md`](IDEAS.md).

## How to use this document

- Keep content execution-oriented (scope, status, sequencing, blockers, and exit criteria).
- Log concrete shipped increments in the sprint progress section.
- When priorities shift, update sprint goal, checklist, and exit criteria together.

---

## Current implementation focus (Q2 2026)

1. Complete remaining route decomposition and reduce `main_routes.py` to a minimal compatibility layer.
2. Harden API/MCP contract parity for validation and error-shape consistency.
3. Improve admin/operator reliability paths (backups, Telegram identity lifecycle, policy observability).
4. Keep docs synchronized so `README.md` stays concise and `docs/*` remain canonical.

---

## Sprint 3 (Completed) — MCP + Docs Consolidation

### Goals
1. Expand MCP automation coverage with create operations.
2. Increase MCP negative-path and contract validation coverage.
3. Consolidate docs structure and clarify MCP/API behavior references.

### Delivered
- ✅ Added MCP create tools for member/proposal/poll flows.
- ✅ Added happy-path and negative-path MCP tests across create operations.
- ✅ Added/expanded docs index and testing documentation (`docs/INDEX.md`, `docs/TESTING.md`).
- ✅ Expanded APIDOC/SPEC MCP sections including error-code conventions and request examples.
- ✅ Added MCP tool discovery regression coverage to prevent missing create tool advertisement.

### Exit Criteria
- MCP create tools fully tested across success and key failures.
- APIDOC and SPEC aligned on MCP tool surface and constraints.
- Documentation structure supports concise README linking.

**Status:** ✅ Completed.

---

## Sprint 4 (In Progress) — Route Finalization + Admin Reliability

### Goals
1. Finish extraction of remaining route logic from `main_routes.py`.
2. Strengthen operator-facing admin reliability and UX continuity.
3. Maintain strict parity expectations between REST and MCP validation behavior.

### Delivered so far
- ✅ Migrated additional handlers from `main_routes.py` into blueprint modules while preserving compatibility shims.
- ✅ Expanded endpoint alias regression tests to protect `url_for(...)` compatibility during migration.
- ✅ Added admin Telegram unlink support and regression coverage.
- ✅ Added backup download endpoint validation/serving improvements and admin UI table presentation updates.
- ✅ Added admin tab persistence behavior so section context survives postback/reload.
- ✅ Added backup download audit events for both success and rejection paths, including timestamp and reason-code metadata.
- ✅ Preserved admin tab context on backup-download redirect error paths via `tab` query propagation.
- ✅ Added backup lifecycle audit events for admin-triggered backup creation and failure paths (`admin_backup_created`, `admin_backup_failed`).
- ✅ Added regression coverage for backup lifecycle audit events across both DB and image backup success/failure paths.
- ✅ Reframed `docs/IDEAS.md` to forward-looking roadmap content only.
- ✅ Hardened Telegram poll vote identity enforcement for `telegram_require_linked_vote=true` (no fallback match by app username).
- ✅ Added Telegram webhook/dispatch regression coverage for linked-account rejection messaging, plus testing-doc updates.
- ✅ Unified poll/proposal Telegram `link_required` rejection text path and added regression coverage to keep operator/member UX consistent.
- ✅ Consolidated Telegram link-state SQL classification into a shared service helper to keep REST/MCP diagnostics logic in lockstep.
- ✅ Added structured Telegram link lifecycle audit events for link + unlink actions across command, member settings, and admin-panel flows.
- ✅ Extracted Telegram link/unlink persistence logic into `app/services/telegram_link_service.py` to reduce route-level DB orchestration.

### Remaining work (execution checklist)
1. **Route decomposition closure**
   - Move any remaining substantial handler logic out of `main_routes.py`.
   - Keep shim layer intentionally thin and measurable.

2. **Admin reliability observability**
   - Expand backup-audit coverage from download events to lifecycle events (`created`, `pruned`, `failed`) with reason codes.
   - Add Telegram link lifecycle metadata exposure and operational diagnostics.

3. **REST/MCP contract parity pass**
   - Add additional parity tests for shared business-rule boundaries.
   - Verify consistent machine-readable error semantics across interfaces.

4. **Docs synchronization pass**
   - Keep `APIDOC.md`, `SPEC.md`, `TESTING.md`, and sprint notes aligned for any contract or workflow change.

### Exit Criteria
- `main_routes.py` is reduced to compatibility routing with minimal orchestration logic.
- Admin reliability operations are observable through logs/events without ad-hoc DB inspection.
- REST and MCP validation/error contracts are consistent for high-value endpoints/tools.
- Docs remain synchronized with implementation behavior.

**Status:** 🟡 In Progress.

---

## Sprint 5 (Planned) — Contract Matrix + Service Boundary Completion

### Planned scope
1. Finalize service/repository boundaries for remaining admin/proposal write operations.
2. Expand API contract matrix tests (success + rejection paths) for core REST endpoints.
3. Remove transitional endpoint aliases once all callers/templates are blueprint-native.

### Planned exit criteria
- Write paths route through service entry points with clear repository ownership.
- Contract tests enforce stable API behaviors for core endpoints.
- Alias cleanup completes without endpoint regressions.

**Status:** ⚪ Planned.
