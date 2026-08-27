# SPRINTS — Implementation Planning and Progress Tracking

Last updated: 2026-08-26

This document tracks implementation sequencing, active sprint scope, and completion status.
Backlog strategy and long-range direction live in [`IDEAS.md`](IDEAS.md).

## How to use this document

- Keep content execution-oriented (scope, status, sequencing, blockers, and exit criteria).
- Log concrete shipped increments in the sprint progress section.
- When priorities shift, update sprint goal, checklist, and exit criteria together.

---

## Current implementation focus (Q3 2026)

1. Complete remaining route decomposition and reduce `main_routes.py` to a minimal compatibility layer.
2. Harden API/MCP contract parity for validation and error-shape consistency.
3. Improve admin/operator reliability paths (backups, Telegram identity lifecycle, policy observability).
4. Make the Telegram natural-language assistant safe under multiple application workers and
   cover its webhook lifecycle end-to-end (see `IDEAS.md` P0 items).
5. Keep docs synchronized so `README.md` stays concise and `docs/*` remain canonical.

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
4. Ship and harden the Telegram natural-language assistant (MCP-backed), added mid-sprint
   as a new scope area alongside the original three goals.

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
- ✅ Shipped the MCP-backed Telegram natural-language assistant (`app/integrations/telegram_agent.py`):
  database-backed allowlist, bounded model-request queue, mutation confirmation via
  `/confirm`/`/cancel` with a bounded TTL, and Telegram-limit-aware chunked replies.
- ✅ Restricted the assistant's MCP tool registry to an explicit allowlist and excluded
  `create_member` from Telegram entirely; redacted password/secret/token/API-key fields
  from confirmation display arguments.
- ✅ Moved webhook update deduplication and pending-confirmation state to SQLite so they
  are shared across application workers and survive restarts, with atomic consume before
  execution.
- ✅ Hardened MCP JSON-RPC parameter validation and Telegram account-linking flows.
- ✅ Added canonical, privacy-reviewed REST/MCP user-statistics and Telegram member-link
  diagnostics services with parity tests, including an administrator-only `include_email`
  opt-in (email is withheld by default).
- ✅ Hardened Telegram group message addressing (`@mention`/reply/`bot_command` entity
  matching) and added forum-topic-aware routing so a configured `TELEGRAM_CHAT_ID` +
  `TELEGRAM_THREAD_ID` topic behaves as an always-on assistant conversation, with replies
  correctly threaded back via `message_thread_id`/`reply_parameters`.
- ✅ Normalized Telegram's group-only `/confirm@botname` and `/cancel@botname` syntax.
- ✅ Extended backup lifecycle audit events beyond admin-triggered backups: the daily
  APScheduler jobs and the startup auto-backup check now emit the same structured
  `*_backup_created`/`*_backup_failed` events (`scheduled_backup_*`, `startup_backup_*`)
  with `pruned_count`/`error` metadata, so routine automatic backups are no longer
  silent. Regression coverage added in `tests/test_backup_service.py` and
  `tests/test_app_startup.py`.
- ✅ Added `members.last_linked_at`/`last_unlinked_at`, set on every link (`/link`
  command or an OIDC login carrying a Telegram identity) and unlink (admin or member
  self-service), and exposed on `GET /api/members/telegram` and
  `list_member_telegram_links` for operator diagnostics.
- ✅ Fixed a pre-existing test-isolation bug in `tests/test_oidc_auth.py`: four tests
  using the `isolated_db_path` fixture never pointed `main_routes.DB_PATH` at it, so they
  silently ran against the shared session database instead of an isolated one — the
  extra write volume from the change above made this consistently fail as lock
  contention rather than occasionally. Fixed by mirroring the one test that already did
  this correctly.
- ✅ Moved Telegram conversation history to the same SQLite-backed, shared-across-workers
  pattern already used for pending confirmations (`telegram_conversation_history`,
  `configure_history_store`), bounded to the last 12 turns per chat/user.
- ✅ Added REST/MCP parity tests for `create_proposal` and `create_poll`, and fixed two
  real drifts they caught: REST's `basic_supplies` field silently coerced any truthy
  value (including the JSON string `"false"`) instead of validating it like MCP already
  did, and MCP's `create_proposal` uniquely classified a non-positive `created_by` as an
  invalid-params error instead of not-found, unlike REST and MCP's own `create_poll`.
- ✅ Added the end-to-end natural-language webhook contract test
  (`tests/test_telegram_natural_language_webhook.py`) that drives the real webhook route:
  unlinked senders are silently ignored, linked senders get a thinking message that's
  deleted after a real tool-call round trip and final reply delivery, a full queue
  returns the busy notice and still cleans up the thinking message, a duplicate
  `update_id` isn't reprocessed, and an admin's propose → `/confirm` flow creates
  exactly one proposal — while a role removed between the two leaves zero.

Remaining Telegram-assistant hardening (a process-local model-request queue that needs an
architectural decision rather than a like-for-like SQLite swap, an end-to-end webhook
contract test, public MCP application boundary, background-job observability, fair-use
limits, and confirmation audit records) is tracked as forward-looking backlog in
[`IDEAS.md`](IDEAS.md) rather than duplicated here.

### Remaining work (execution checklist)
1. **Route decomposition closure** — close to done (2026-08-27): `main_routes.py` cut from
   2368 to 873 lines (-63.1%).
   - Moved the entire `/admin` handler (627 lines: every member/budget/settings/poll/
     backup admin action, plus the dashboard's data-gathering tail) from `main_routes.admin()`
     into `admin_routes.py`'s blueprint view — it previously just delegated to
     `legacy.admin()`. Same route, same decorators (`@limiter.exempt @login_required
     @admin_required`), same behavior; only its home module changed.
   - Moved all 11 proposal-lifecycle handlers (`new_proposal`, `proposal_detail`,
     `edit_comment`, `delete_comment`, `delete_proposal`, `edit_proposal`, `quick_vote`,
     `withdraw_vote`, `undo_approve`, `mark_purchased`, `unmark_purchased`) from
     `main_routes.py` into `proposal_routes.py` the same way.
   - Moved `proposals()` (the main listing page, ~155 lines) into `proposal_routes.py` as
     a real blueprint route (`proposals.proposals`); `main_routes.py` now carries only a
     3-line compatibility alias at the bare `proposals` endpoint, matching the existing
     `/about`/`/budget` pattern — needed because dozens of call sites still do
     `url_for("proposals")`/`redirect(url_for("proposals"))` unqualified. Dropped a
     pre-existing dead `from flask import make_response` local import and the now-unused
     `date`/`timedelta`/`timezone` top-level imports while moving it.
   - Shared helpers each handler still needs (`get_db`, `get_current_budget`,
     `process_proposal`, `TelegramClient`, etc.) are re-read from `main_routes` as local
     variables *inside* each view on every request (`get_db = legacy.get_db`, ...) rather
     than imported once at module load — this preserves every existing test's ability to
     `patch("app.web.routes.main_routes.X", ...)` and keeps module-level state like
     `DB_PATH` live. One test (`test_admin_unlink_telegram_action_emits_audit_event`) had
     to be repointed at the function's new home (`admin_routes.log_telegram_link_event`)
     since that's a genuine, correct change in where the call now lives.
   - Moved `telegram_webhook` (~180 lines) into a new `telegram_routes.py` blueprint,
     registered in `app/web/routes/__init__.py`. No `url_for("telegram_webhook")` call
     sites exist anywhere (the webhook URL is always built as a plain string,
     `f"{base_url}/telegram/webhook/{secret}"`, for Telegram's own `setWebhook` call),
     so this one needed no compatibility alias at all — the route was simply deleted
     from `main_routes.py`. Module-level singletons the webhook depends on
     (`_telegram_agent_executor`, `_telegram_update_deduplicator`,
     `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`/etc., `TelegramClient`) stayed defined in
     `main_routes.py` and are re-read fresh from `legacy.X` inside the view, same as
     every other move — this is what keeps the ~120 existing test references to
     `main_routes.TELEGRAM_*`/`main_routes.TelegramClient`/etc. working unchanged.
   - `main_routes.py`: 2368 → 873 lines (-63.1%) since this work started. Cleaned up
     seven now-dead imports (`hmac`, `requests`, `limiter`, `csrf`,
     `get_telegram_principal`, and the six `telegram_webhook`-only helpers from
     `app.integrations.telegram_webhook`) left behind by the move.
   - Full suite re-run after each move (three times for this one, given ~120 test
     references into the moved code); no behavior regressions, only the one expected
     test-location fix noted above.
   - Noticed but not changed: `app/web/routes/__init__.py` already has a generic
     `legacy_endpoint_aliases` dict that re-registers a blueprint view under its old
     bare endpoint name for `url_for()` compatibility (used for the 11 proposal
     handlers, `admin`, `polls_page`, etc.). The `proposals()` move in the previous
     commit predates noticing this and instead kept a manual `@app.route("/proposals")`
     wrapper in `main_routes.py` — functionally equivalent, but adding `"proposals":
     "proposals.proposals"` to that dict instead would be the more consistent cleanup;
     left as a small follow-up rather than reworking an already-tested commit.
   - Remaining: the ~30 shared helpers underneath all of this (`get_db`, threshold/
     vote-mode calculations, Telegram command processors, `record_proposal_vote`, etc.)
     are a separate, larger undertaking — moving *those* into
     `app/services/`/`app/repositories/` is WS-A A2's service/repository boundary work,
     not route decomposition itself. With `admin()`, the proposal handlers,
     `proposals()`, and `telegram_webhook` all relocated, route decomposition itself is
     close to done; what's left in `main_routes.py` is almost entirely that shared
     helper layer plus small compatibility shims.

1b. **Service/repository boundary (WS-A A2)** — started (2026-08-27): extracted the
   poll/proposal vote-mode policy logic (`get_poll_vote_mode`,
   `is_web_poll_voting_enabled`, `is_telegram_poll_voting_enabled`,
   `require_linked_telegram_for_votes`, `get_proposal_vote_mode`,
   `is_web_proposal_voting_enabled`, `can_record_proposal_vote`,
   `is_registration_enabled`) into `app/services/voting_mode_service.py`. Each function
   takes `get_setting_value` as an explicit parameter rather than reaching for a module
   global, making the policy directly unit-testable without a DB or Flask context — see
   the 6 new tests in `tests/unit/test_services.py`. `main_routes.py` keeps one-line
   wrappers at the original names so every blueprint's existing `legacy.X` access and the
   ~15 tests that patch `main_routes.X` for these names keep working unchanged. Full suite:
   492 passed (486 + 6 new), same 4 pre-existing/environmental failures, zero regressions.
   Second slice (2026-08-27): extracted `close_expired_polls` and
   `build_poll_results_message` into `app/services/poll_service.py` — a straight
   relocation, since both already took `conn` as their only DB dependency with no module
   globals. `main_routes.py` keeps one-line wrappers at the original names as before.
   `tests/unit/test_poll_closing.py`'s three tests now call `poll_service.X` directly
   instead of `main_routes.X`, since they already built an isolated in-memory DB rather
   than depending on Flask/app internals — direct service-level coverage per A2's stated
   goal, no loss of behavior checked. Full suite: 492 passed, same 4 pre-existing/
   environmental failures, zero regressions.
   Third slice (2026-08-27): extracted `process_telegram_vote_command`,
   `process_telegram_vote_callback`, and `process_telegram_proposal_vote_command`
   (~150 lines of `/vote`/`/pvote` parsing, member lookup, and vote-recording logic) into
   `app/services/telegram_command_service.py`, taking `get_db`, `get_setting_value`,
   `send_telegram_message`, and/or `record_proposal_vote` as explicit parameters. 12 new
   tests in `tests/unit/test_telegram_command_service.py` exercise it directly against a
   throwaway sqlite file — no Flask, no monkeypatching. `main_routes.py` keeps one-line
   wrappers as before. Left `process_telegram_link_command` where it is — it's already a
   thin adapter over the existing `process_link_command` service plus one audit-log call,
   so moving it would trade one call site for four injected parameters with no logic
   gained. Full suite: 504 passed (492 + 12 new), same 4 pre-existing/environmental
   failures, zero regressions.
   Remaining A2 scope (`get_db`/settings reads, `record_proposal_vote`/
   `log_proposal_vote_event`, `process_telegram_link_command`, Telegram messaging/
   webhook-sync helpers — see `IDEAS.md` A2 for the complete remaining list) is unchanged
   and still open; more slices planned.

1c. **Fixed the "4 pre-existing/environmental failures" every note above cited without
   root-causing (2026-08-27)** — full details in `IDEAS.md`'s "Fixed: the 4 tests
   repeatedly labeled..." entry under A2. Short version: two real template bugs in
   `templates/proposals.html` (missing CSS classes on the `approved`/`over_budget` status
   badges, no badge at all for `rejected`, and an "All" filter button that silently
   behaved like "Active"), fixed alongside a test that depended on ambient shared-DB
   state instead of seeding its own fixtures; plus all four `test_production_config.py`
   subprocess calls using bare `"python"` instead of `sys.executable`, which broke under
   this sandbox's mismatched system `cryptography`/`cffi` install. Full suite is now
   **511 passed, 0 failed**, no `-k` exclusion needed — `pytest -q tests/` is the correct
   command going forward.

2. **Admin reliability observability** — ✅ closed for this sprint's scope.
   - Backup-audit coverage now spans download, admin-triggered, scheduled, and
     startup-check lifecycle events (`created`/`failed` with `pruned_count`/reason
     codes) — see Delivered above.
   - Telegram link lifecycle metadata (`last_linked_at`/`last_unlinked_at`) is now
     exposed via REST/MCP — see Delivered above. Reason-coded audit events for
     policy-blocked votes remain open (`IDEAS.md` item 5).

3. **REST/MCP contract parity pass**
   - Add additional parity tests for shared business-rule boundaries.
   - Verify consistent machine-readable error semantics across interfaces.
   - ✅ `create_proposal`/`create_poll` covered — see Delivered above. Remaining:
     pagination/type errors across list endpoints (`IDEAS.md` item 4).

4. **Docs synchronization pass**
   - Keep `APIDOC.md`, `SPEC.md`, `TESTING.md`, and sprint notes aligned for any contract or workflow change.

5. **Telegram-assistant reliability closure**
   - Conversation history is now shared across workers (see Delivered above). Remaining:
     decide an approach for the process-local model-request queue (`IDEAS.md` P0 item on
     shared state for multi-worker/restart safety).
   - ✅ The end-to-end natural-language webhook contract test called for in `IDEAS.md` is
     done — see Delivered above.

### Exit Criteria
- `main_routes.py` is reduced to compatibility routing with minimal orchestration logic.
- Admin reliability operations are observable through logs/events without ad-hoc DB inspection.
- REST and MCP validation/error contracts are consistent for high-value endpoints/tools.
- Docs remain synchronized with implementation behavior.
- The Telegram assistant is safe to run behind multiple application workers without losing
  pending confirmations or conversation state.

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
