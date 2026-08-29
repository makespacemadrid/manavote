# SPRINTS — Implementation Planning and Progress Tracking

Last updated: 2026-08-28

This document tracks implementation sequencing, active sprint scope, and completion status.
Backlog strategy and long-range direction live in [`IDEAS.md`](IDEAS.md).

## How to use this document

- Keep content execution-oriented (scope, status, sequencing, blockers, and exit criteria).
- Log concrete shipped increments in the sprint progress section.
- When priorities shift, update sprint goal, checklist, and exit criteria together.

---

## Current implementation focus (Q3 2026)

Sprints 3 through 8 are complete. Sprint 7 delivered the UX/UI, budget-visualization,
and member-feedback work scoped from the dedicated UX audit. Sprint 8 then completed
the public MCP application boundary: JSON-RPC and Telegram now share a transport-neutral
execution layer with explicit actor policy. Sprint 9 completed reliable proposal-resource discovery and sharing through Telegram
natural chat, including missing-Base-URL operator diagnostics. Forward-looking work is
tracked in [`IDEAS.md`](IDEAS.md) until the next sprint is scoped.

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

## Sprint 4 (Completed 2026-08-27) — Route Finalization + Admin Reliability

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
   Fourth and fifth slices (2026-08-27): extracted `record_proposal_vote`/
   `log_proposal_vote_event` into `app/services/proposal_vote_recording_service.py`
   (taking `get_db`, `get_setting_value`, `process_proposal`, and `logger` as explicit
   parameters), and `send_telegram_message`/`send_telegram_admin_test_message`/
   `sync_telegram_webhook`/`sync_telegram_webhook_on_startup` into
   `app/services/telegram_messaging_service.py` (taking the `TelegramClient` class itself
   as a parameter rather than importing it — tests replace `main_routes.TelegramClient`
   wholesale with a fake, so the service must re-resolve it from the caller on every call,
   same reasoning as every prior injection). 17 new direct unit tests across both modules.
   Also removed `migrate_password_if_needed` from `main_routes.py`: confirmed via grep
   it was dead code, fully superseded by `app.services.auth_service.verify_and_migrate_password`
   (already used by the real login path in `auth_routes.py`) and called by nothing, so this
   was deletion, not extraction. `main_routes.py`: 627 → 545 lines since this checklist
   item's last update. Full suite: 524 passed, zero regressions.
   Remaining A2 scope is now just `get_db`/settings-budget read wrappers (already
   appropriately thin) and `process_telegram_link_command` (deliberately left, see third
   slice above) — everything else originally scoped for A2 is done.

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

3. **REST/MCP contract parity pass** — ✅ closed for this sprint's scope.
   - Add additional parity tests for shared business-rule boundaries.
   - Verify consistent machine-readable error semantics across interfaces.
   - ✅ `create_proposal`/`create_poll` covered — see Delivered above.
   - ✅ Pagination/type errors across list endpoints (2026-08-27): added REST/MCP parity
     tests for `list_proposals` (this was a coverage gap only — REST already validated
     correctly). Found and fixed a real drift for `list_polls`: MCP already supported
     `limit`/`offset`, but REST's `GET /api/polls` had none at all (hardcoded `LIMIT 100`).
     Added matching pagination support and validation to `GET /api/polls`, documented in
     `APIDOC.md`, with parity tests for both the success and rejection paths. Full details
     in `IDEAS.md` item 4.

4. **Docs synchronization pass**
   - Keep `APIDOC.md`, `SPEC.md`, `TESTING.md`, and sprint notes aligned for any contract or workflow change.

5. **Telegram-assistant reliability closure** — ✅ closed (2026-08-27).
   - Conversation history is now shared across workers (see Delivered above).
   - ✅ The end-to-end natural-language webhook contract test called for in `IDEAS.md` is
     done — see Delivered above.
   - ✅ Decided the process-local model-request queue architecture question (asked of and
     decided by the user, full reasoning in `IDEAS.md`'s "Shared state for multi-worker/
     restart safety" entry): the bounded worker pool stays process-local by design, since
     the only state where cross-worker visibility is a correctness requirement
     (confirmations, dedup, conversation history) is already durable, and the residual
     risk — an in-flight reply lost if the process crashes mid-job — costs one missed
     chat reply, not a lost vote or mutation. Building a persistent job queue to close
     that narrow gap was judged disproportionate to what this app's scale needs. What
     *was* fixed: `_answer_and_send` had no catch-all, so `concurrent.futures` silently
     dropped any exception outside a narrow expected-error tuple — including a failure in
     the outbound Telegram delivery call itself. Added logging + a graceful user-facing
     fallback at every stage, with a regression test forcing an unhandled exception type
     and asserting it's caught, logged, and answered rather than silently lost.

### Exit Criteria
- ✅ `main_routes.py` is reduced to compatibility routing with minimal orchestration logic
  (2368 → 545 lines, -77%; remaining content is DB bootstrap, thin repository/service
  wrappers kept for `legacy.X` compatibility, and Flask route-registration shims).
- ✅ Admin reliability operations are observable through logs/events without ad-hoc DB inspection.
- ✅ REST and MCP validation/error contracts are consistent for high-value endpoints/tools.
- 🟡 Docs remain synchronized with implementation behavior (ongoing, not a one-time gate).
- ✅ The Telegram assistant is safe to run behind multiple application workers without losing
  pending confirmations or conversation state — pending confirmations, update
  deduplication, and conversation history are all SQLite-backed and shared; the
  model-request queue's process-local scope is a documented, deliberate design decision
  (see item 5), not an open gap.

**Status:** ✅ Completed (2026-08-27). Item 1b's "remaining" `get_db`/settings-budget read
wrappers and `process_telegram_link_command` are intentional final states (already
appropriately thin / deliberately left, not unfinished work — see the reasoning in each
progress note), and docs-sync is an ongoing practice rather than a gate. Every checklist
item and exit criterion above is closed.

---

## Sprint 5 (Completed 2026-08-27) — MCP/REST Convergence + Exception Hygiene

### Why this scope
Sprint 4's A2 work (moving `main_routes.py`'s embedded logic into
`app/services/`/`app/repositories/`) wasn't just cleanup — applying it directly caught two
real REST/MCP behavior drifts (`basic_supplies` coercion, `created_by` error-code
mismatch) and one real feature gap (polls pagination missing from REST). All three
existed *because* REST and MCP independently reimplemented the same query/validation
logic instead of sharing it. `app/mcp_server.py` (872 lines, 17 direct SQL call sites for
proposal listing, poll listing/creation, voting-setting reads/writes, and member
creation) is the last large block of that pattern — this is IDEAS.md's "MCP extraction
boundary (P1)" item, and finishing it is the highest-leverage thing left: it doesn't just
document parity, it makes future drift structurally harder to introduce.

### Goals
1. **MCP extraction boundary** — ✅ closed (2026-08-27), see the three slices below.
   Move `app/mcp_server.py`'s embedded proposal-listing,
   poll-listing/creation, voting-setting, and member-creation logic into
   `app/services/`/`app/repositories/` modules shared with the equivalent REST routes,
   one use case at a time (same incremental, test-verified-after-each-slice approach used
   for A2). Closes IDEAS.md's "MCP extraction boundary (P1)" and is the natural
   system-wide conclusion of WS-A A2, which only covered `main_routes.py`.
   - Slice 1 (2026-08-27): compared each MCP list tool against its REST counterpart
     first, before extracting anything. `list_proposals`/`list_polls` have genuinely
     different response shapes on purpose (votes vs. creator username), so forcing one
     shared query would be a product decision, not a safe refactor — left those alone.
     What *is* identical everywhere is limit/offset validation: extracted into
     `app/services/pagination_service.py` (`parse_limit_offset`, transport-agnostic), now
     used by REST's `parse_pagination_params` and all 5 of MCP's previously-duplicated
     pagination blocks (`list_proposals`, `list_polls`, `list_user_statistics`,
     `list_group_purchases`, `list_member_telegram_links`).
   - Slice 2 (2026-08-27): voting settings' write path (REST `PUT /api/settings/voting`
     and MCP `update_voting_settings`) ran identical SQL — extracted into
     `app/services/voting_settings_service.py` (`apply_voting_settings`). Also
     deduplicated the vote-mode validation set, previously defined three separate times.
     Deliberately left the *read* path alone (MCP batches all three settings in one
     query with no Flask app context to share; REST reads through `main_routes`'s
     Flask-coupled single-key getters) — no shared behavior to converge there, only a
     different, equally-valid implementation strategy per transport.
   - 11 new direct unit tests (`tests/unit/test_pagination_service.py`,
     `tests/unit/test_voting_settings_service.py`). `app/mcp_server.py`: 872 → 850 lines.
     Full suite: 543 passed, zero regressions.
   - Slice 3 (2026-08-27): `create_proposal`'s actual persistence (the INSERT plus the
     "auto-clear `basic_supplies` over €20" business rule) was duplicated in full between
     REST and MCP — moved to `ProposalRepository.create()` (existing
     `app/repositories/proposal_repo.py`). `create_poll`'s INSERT moved to a new
     `PollRepository.create()` (new `app/repositories/poll_repo.py`). Found MCP's
     `create_poll` had its own hand-rolled option validation instead of using the
     already-shared `normalize_poll_options` — a real drift risk of the same shape as
     the `basic_supplies` bug. Since `mcp_server.py` must stay Flask-free, moved
     `normalize_poll_options`/`parse_positive_amount` out of the Flask-importing
     `api_helpers.py` into a new `app/services/creation_validation_service.py`;
     `api_helpers.py` re-exports them so existing callers are unaffected. Fixed two
     tests that had monkeypatched the old persistence mechanism
     (`mcp_server._db_execute`) to instead monkeypatch `PollRepository.create` — the
     refactor moved the mockable seam, not what the tests verify. 12 new direct unit
     tests. `app/mcp_server.py`: 850 → 845 lines. Full suite: 555 passed, zero
     regressions.
   - Remaining: `create_member`/`list_group_purchases` have no REST equivalent to
     converge with, so they stay MCP-only for this goal. `list_proposals`/`list_polls`
     response-shape convergence remains an explicit non-goal unless a product decision
     says otherwise (see slice 1). Full details in `IDEAS.md`.
2. **Route exception granularity** — replace the 19 broad `except Exception` blocks
   across 8 files (`mcp_server.py`, `backup_service.py`, `main_helpers.py`,
   `api_routes.py`, `poll_routes.py`, `admin_routes.py`, `telegram_routes.py`,
   `auth_routes.py`) with typed exceptions and stable reason codes, so failures are
   diagnosable instead of collapsing into one generic message. Closes IDEAS.md's "Route
   exception granularity (P0)".
   - Slice 1 (2026-08-27): removed all four broad catches from `poll_routes.py` and
     `main_helpers.py`. Poll database failures now catch `sqlite3.Error` and log stable
     `poll_lookup_failed`, `poll_list_failed`, or `poll_votes_load_failed` reason codes
     with the relevant poll ID. Timezone lookup now catches only the database, row-shape,
     and timezone-data failures it can safely fall back from, and reliably closes an
     opened connection. The same slice typed the proposal-update API and admin poll-list
     catches as `sqlite3.Error`, retaining the API's existing `proposal_update_failed`
     code and adding reason-coded operator logs. The remaining broad-catch count is 13
     across 5 files. The full-suite run also exposed a second status-rendering test that
     still depended on an active proposal left by unrelated tests; it now owns and
     removes its fixture, so repeated full-suite runs remain deterministic.
   - Slice 2 (2026-08-27): ✅ closed the remaining 13. Backup jobs and admin actions now
     share typed filesystem/archive/configuration failures and the stable
     `backup_io_error`, `backup_archive_error`, and `backup_configuration_error` codes;
     APScheduler is a declared dependency and scheduler startup catches its typed
     already-running failure. OIDC catches Authlib/Jose/request/claim-validation errors
     with `oidc_token_exchange_failed`. MCP's JSON-RPC and TCP boundaries catch explicit
     application failures, log `application_failure`, and no longer disclose exception
     text to clients. Telegram's worker stages use an explicit failure tuple, while a
     future callback records truly unexpected worker crashes as
     `unexpected_worker_failure`. No `except Exception` remains anywhere under `app/`.
3. **Background-job observability** — attach `update_id`, chat ID, actor member ID, tool
   name, queue-wait time, model latency, and a stable reason code to structured logs for
   the Telegram assistant's background jobs; add graceful executor shutdown. ✅ Completed
   2026-08-27: job start/completion/rejection, every model round, and every tool call now
   emit structured `telegram_assistant_job` records with the requested correlation and
   timing fields; process exit gracefully drains and shuts down the bounded executor.
   Advances IDEAS.md's broader "Background-job observability and lifecycle (P1)" item;
   aggregate counters and MCP-specific latency remain a future operational-metrics
   enhancement.
4. **Telegram group-routing hardening (small, cheap)** — add a startup warning when a
   Telegram group integration is configured without `TELEGRAM_BOT_USERNAME` set, since
   `is_natural_language_message` currently treats that as "match any mention," which is
   silently over-permissive in a multi-bot group. ✅ Completed 2026-08-27: startup now
   emits the stable `missing_bot_username_for_group` reason code for a negative Telegram
   chat ID or configured forum thread without a bot username; private chats do not
   produce a false-positive warning. Closes the P2 gap flagged in the forum-topic
   routing audit.

### Explicitly deferred (with reasoning, not just left off)
- **WS-C C4, query/index optimization** — needs `EXPLAIN QUERY PLAN` results against
  production-like row counts to make an evidence-based call; this app's actual data
  volume doesn't yet justify guessing at indexes. Revisit when real usage data exists.
- **WS-C C3, proposal lifecycle state machine** — a real structural change (centralizing
  legal status transitions), better scoped as its own sprint once Goal 1 above gives
  proposal status logic one canonical home to centralize *into*, rather than layering a
  state machine on top of logic still split across REST/MCP/routes.
- **Fair-use limits/cancellation, conversation quality controls** (IDEAS.md Telegram-audit
  items 6 and 8) — same reasoning as Sprint 4's model-request-queue decision: this app's
  current scale doesn't show signs of needing per-user rate limits or token budgeting
  yet, and adding them speculatively risks solving a problem that doesn't exist while
  adding real complexity (cooldown UX, fairness policy). Revisit if usage patterns change.
- **Full UX/Design track** — needs product/design ownership and human review of visual
  changes before an autonomous coding pass should touch it; not a fit for this sprint.
- **WS-C C1, standard error envelope** — already effectively delivered: `api_error()`
  (`{"error": {"code", "message"}}`) is used consistently across all 27 REST error sites
  in `api_routes.py` with no ad hoc alternative shape found. No new work needed; marking
  closed rather than carrying it forward as if open.

### Resolved before this sprint started
- **OIDC/SSO silent-attach-by-email trust model** (`docs/IDEAS.md`, "Docs audit findings
  requiring a product decision") — ✅ answered (2026-08-27): SSO is the single source of
  truth for identity and authority; password login is a legacy path only. Most legacy
  members deliberately set their own `email` so their SSO login attaches to their
  existing account and preserves history — the current behavior is exactly the intended
  design, not a gap to close. This is also structurally safe on the admin-role question
  the original audit note raised: `is_admin` is recomputed from the token's `groups`
  claim on every login and unconditionally overwrites the local value, so an email match
  only decides which account/history a login attaches to — it never grants privilege by
  itself. No code change needed; full reasoning in `IDEAS.md`.

### Exit criteria
- ✅ MCP's proposal/poll/member/voting-setting logic routes through the same
  services/repositories REST uses, with no remaining large blocks of inline SQL in
  `app/mcp_server.py` for those use cases. MCP-only member/group-purchase operations and
  intentionally different list response shapes are documented non-convergence cases,
  not duplicated REST business logic (see Goal 1).
- ✅ No bare `except Exception` remains in a route/service handler without a typed
  exception and reason code behind it.
- ✅ Telegram background-job logs carry enough structured fields to diagnose a stuck or
  failed request without reading source code.
- ✅ The OIDC trust-model question has an explicit answer — resolved before this sprint
  started; see "Resolved before this sprint started" above.

**Status:** ✅ Completed (2026-08-27). All four goals and exit criteria are closed.
MCP-specific latency/counters remain an explicitly documented operational enhancement,
not missing request-level diagnostics; the larger public MCP application boundary stays
in `IDEAS.md` for future sprint scoping.

---

## Sprint 6 (Scoped 2026-08-27) — Confirmation Integrity + Remaining Telegram Observability

### Why this scope
Sprint 5 brought reason-coded, structured audit logging to almost every operational
boundary in the app: backups (admin/scheduled/startup), Telegram link/unlink, startup
health, MCP transport errors, OIDC failures, and the assistant's background jobs. The one
place that standard hasn't reached yet is the highest-stakes path the assistant has: the
`/confirm` mutation flow. Verified directly against `app/integrations/telegram_agent.py`
(2026-08-27) — `PendingAction` carries `tool_name`, `arguments`, `actor_member_id`, and
`created_at` only: no tool-schema version, no digest of the arguments that will actually
execute, and no audit event is emitted anywhere in the propose/confirm/cancel/expire path.
That's a real gap given `/confirm` is the only way this app lets an LLM-driven request
reach a write operation. Two smaller, already-scoped-in-`IDEAS.md` observability items
round out the sprint since they're cheap to close now that the structured-logging pattern
(reason codes, correlation IDs) is well established everywhere else.

### Goals
1. **Confirmation integrity and auditability** — ✅ closed 2026-08-27. Closes `IDEAS.md`'s
   item 7 (P1).
   - ✅ `PendingAction` now captures `schema_fingerprint` (a hash of the tool's current
     `inputSchema` at propose time, via a new `_schema_fingerprint()`) and
     `arguments_digest` (a hash of the arguments that will execute, via `_stable_digest()`).
     `/confirm` recomputes both and rejects (`schema_changed`, `arguments_tampered`) on a
     mismatch, so a confirmed mutation is provably the one that was proposed rather than a
     stale or corrupted row executing against a contract that no longer matches. Both
     fields are `None`-tolerant for backward compatibility with any pending action already
     in flight from before this migration (the checks are skipped rather than treated as a
     forced mismatch).
   - ✅ New `telegram_pending_actions.schema_fingerprint`/`arguments_digest` columns via
     `add_column_if_missing`, plus updated `CREATE TABLE` for fresh installs
     (`app/db/migrations.py`, `app/db/schema.sql`).
   - ✅ Every mutation lifecycle step now emits a `telegram_assistant_mutation` reason-coded
     audit record via a new `_log_mutation_event()`: `proposed`, `confirmed`, `completed`,
     `failed` (`mcp_error`), `cancelled` (`user_cancelled` or `reset_command`), `expired`
     (`confirmation_ttl_exceeded`), and `rejected` (`not_admin`, `actor_changed`,
     `arguments_tampered`, `schema_changed`). Deliberately a separate event stream from
     `telegram_assistant_job` (job-level timing for every assistant request) rather than
     folded into it, matching how backup and Telegram-link events already get their own
     dedicated audit trail. Documented in `docs/OPERATIONS.md` with a full reason-code
     table. 5 new tests in `tests/unit/test_telegram_agent.py` (schema-mismatch rejection,
     digest-mismatch rejection, a matching-digest/fingerprint success case, full
     propose→confirm→completed event-sequence assertion via `caplog`, and
     cancel/reset both emitting `cancelled`). Full suite: 568 passed (563 + 5 new), zero
     regressions.
2. **Blocked-vote-by-policy audit events** — ✅ closed 2026-08-27. Closes the remainder of
   `IDEAS.md`'s item 5 (Observability completion for Telegram lifecycle, P2).
   - Verified before implementing: proposal votes already had a `channel_disabled` audit
     event, but only reachable from the Telegram path — `record_proposal_vote`'s internal
     check never actually ran on the web path, since `proposal_routes.py` short-circuited
     with a flash message *before* calling it. Poll votes had no audit infrastructure at
     all, on either channel. `telegram_require_linked_vote` rejections (`link_required`)
     were unaudited on every path.
   - Added `poll_service.log_poll_vote_event()` (mirrors
     `proposal_vote_recording_service.log_proposal_vote_event`'s shape/style exactly —
     `event=... source=... mode=... poll_id=... member_id=... reason_code=...`, so both
     read the same way in logs).
   - Web paths: `poll_routes.py` and `proposal_routes.py` (both `proposal_detail` and
     `quick_vote`) now log `channel_disabled` at their existing early-return sites instead
     of just flashing a message.
   - Telegram paths (`app/services/telegram_command_service.py`): added a `logger`
     parameter (matching the existing DI pattern) threaded through
     `process_telegram_vote_command`, `process_telegram_vote_callback`, and
     `process_telegram_proposal_vote_command`; `main_routes.py`'s three wrappers now pass
     `app.logger`. Audits both `channel_disabled` (poll_vote_mode) and `link_required`
     (`telegram_require_linked_vote`) — the latter closes a real gap since it was
     previously unaudited on every path, not just the ones this slice touched.
   - Found and fixed a real test-hygiene bug while adding coverage: an existing test
     (`test_log_proposal_vote_event_includes_current_mode`) monkeypatched
     `logging.getLogger("test").info` directly instead of using `caplog` — since
     `getLogger` returns the same singleton per name, this permanently overwrote the
     shared `"test"` logger for every other test using that name, silently breaking new
     `caplog`-based assertions added elsewhere in the same full-suite run (passed in
     isolation, failed only when the polluting test ran first). Fixed it and two new
     tests of the same shape to use `caplog` instead.
   - 6 new tests in `tests/unit/test_poll_closing.py` (2) and
     `tests/unit/test_telegram_command_service.py` (4, including one new
     `link_required`-rejection case for proposal votes that had no coverage before).
     Documented the full reason-code table in `docs/OPERATIONS.md`. Full suite: 574
     passed, zero regressions.
3. **Forum-topic/mention routing observability** — ✅ closed 2026-08-27. Closes
   `IDEAS.md`'s forum-topic audit item 2 (P2).
   - `app/integrations/telegram_webhook.py`'s `is_natural_language_message` (a bare
     `bool`) was split into a new `classify_message_addressing(message_ctx,
     bot_username="")` returning a reason code (`private`, `reply_to_bot`, `mentioned`,
     `unaddressed`); `is_natural_language_message` is now a one-line wrapper
     (`!= "unaddressed"`) so every existing caller/test keeps its boolean contract
     unchanged.
   - `telegram_routes.py`'s routing block now computes `addressing_reason` up front,
     applies the existing forum-topic override (promoting an otherwise-`unaddressed`
     message to `forum_topic` when it's in the configured `TELEGRAM_CHAT_ID`/
     `TELEGRAM_THREAD_ID`), and logs a `telegram_routing_decision
     reason_code=... chat_id=... chat_type=... addressed=...` record. Deliberately
     scoped to non-command group/supergroup messages only — private-chat addressing is
     always trivially `private` and not diagnostically interesting, and deterministic
     commands (`/link`, `/vote`, etc.) don't go through this ambiguity at all.
   - Gating condition simplified from the old `is_natural_language_message(...) or
     is_configured_forum_topic(...)` OR-expression to `addressing_reason !=
     "unaddressed"` — same behavior, one source of truth instead of two functions
     evaluated separately.
   - Documented the full reason-code table in `docs/OPERATIONS.md`. 1 new test
     (`test_classify_message_addressing_reason_codes`,
     `tests/unit/test_telegram_webhook_helpers.py`) asserting all four reason codes
     directly, plus the existing `is_natural_language_message`/forum-topic tests
     re-run unchanged to confirm the refactor is behavior-preserving. Full suite: 575
     passed, zero regressions.

**Sprint 6 status: all three goals closed 2026-08-27.**

### Explicitly deferred (with reasoning, not just left off)
- **Public MCP application boundary (`IDEAS.md` item 4, P1)** — real architectural value
  (the assistant currently calls the JSON-RPC handler in-process with the server's own
  API key rather than through a proper application-layer boundary), but it's a bigger,
  higher-risk refactor than anything else in this sprint and doesn't block anything else
  scoped here. Good candidate to lead Sprint 7 once Sprint 6's confirmation-integrity
  work is stable.
- **Proposal lifecycle state machine (WS-C C3)** — still cross-cutting (proposal status
  transitions live across `admin_routes.py`, `proposal_routes.py`, and
  `ProposalService`, none of which Sprint 5's MCP-convergence work touched), so the
  "give it one canonical home first" precondition from Sprint 5's scoping still isn't
  met. Revisit once/if those write paths get their own consolidation pass.
- **Fair-use limits and cancellation (`IDEAS.md` item 6, P1)** — same scale-appropriate
  reasoning as Sprint 4's model-request-queue decision: no evidence this app's actual
  usage needs per-user rate limits or token budgeting yet. Revisit if usage patterns
  change.
- **Statistics scale/query optimization (WS-C C4)** — still needs `EXPLAIN QUERY PLAN`
  results against production-like row counts to make an evidence-based call; this app's
  data volume doesn't justify guessing at indexes yet.
- **WS-D credential hardening / backup validation (P2)** — no evidence of current pain
  (no incident, no rotation need reported); lower urgency than the P1 confirmation-audit
  gap above.

### Exit criteria
- Every `/confirm`-reachable mutation emits a reason-coded audit record covering its full
  lifecycle (proposed through confirmed/cancelled/expired/rejected/failed/completed).
- A confirmed mutation's arguments are provably the same ones that were proposed (digest
  match), and a stale/incompatible tool schema is rejected at confirm time rather than
  executed against a changed contract.
- Blocked votes and Telegram group-routing decisions are diagnosable from structured
  logs alone, matching the standard already set for backups, links, and assistant jobs.

**Status:** ✅ Complete 2026-08-27 — all three goals closed.

---

## Sprint 7 (Scoped 2026-08-27) — UX/UI: Button Layout, Placement, Budget Graph & Feedback

### Why this scope
Sprints 3-6 focused entirely on backend hygiene: MCP/REST convergence, exception
handling, and structured audit logging. None of that touched what members actually
look at. A dedicated UX/UI audit (`docs/IDEAS.md`, "UX/UI audit (2026-08-27)") read every
page template against the app's own design system and found the same story
repeatedly: a real shared system exists (`.card`/`.btn`/`.vote-btn`/`.status`) but is
routinely bypassed by one-off inline styles, so buttons drift in color, placement, and
visual weight across pages that do conceptually the same thing (e.g. proposal voting
vs. poll voting), and the budget graph — the app's single most important piece of
data visualization — has never had a dedicated pass. Goals 1-3 scope directly from
that audit's P1/P2 findings, prioritizing the ones explicitly called out (button
layout/placement, the budget graph) plus the safety-relevant confirmation-UX gaps that
surfaced in the same read. Goal 4 was added by explicit request: members currently
have no in-app channel to report bugs or suggest ideas, visible to admins as a group;
it's scoped end-to-end (schema, service, REST, MCP, admin panel) per `IDEAS.md`'s
"Member feedback / bug reports / suggestions (2026-08-27)", so the Telegram assistant
can store feedback the same way it already handles proposal/poll creation.

### Goals
1. **Consistent, safe confirmation UX for destructive actions.** Closes audit items 3,
   4, 5, 6, 21, 22.
   - Extract `admin.html`'s `dangerActionModal` into a small shared JS/template
     component usable from any page, not just admin — same visual treatment
     everywhere instead of admin getting a styled modal and every other page getting an
     unbranded native `confirm()`.
   - Replace the native `confirm()` calls in `proposal_detail.html` and `proposals.html`
     (delete proposal, delete comment, mark purchased, undo approval) with the shared
     modal.
   - Fix the inconsistency where "undo approval" is confirmed on the detail page but not
     from the proposals list's quick action — both should behave the same way.
   - Convert the bare-GET `undo_approve`/`withdraw_vote` links to POST forms, consistent
     with every other state-changing action in the app.
   - Give the shared modal real dialog semantics: `role="dialog"`, `aria-modal="true"`,
     a focus trap, and Escape-to-close.
   - Make the settings dropdown (`.settings-dropdown:hover`) usable by click/tap, not
     hover-only, without breaking the existing desktop hover behavior.
   - Remove `maximum-scale=1.0, user-scalable=no` from the viewport meta tag
     (`base.html`) — pinch-to-zoom shouldn't be disabled app-wide without a layout
     reason that requires it.
2. **Button placement and visual-hierarchy cleanup on Proposals and Polls.** Closes
   audit items 1, 2, 7, 8, 9, 10, 11, 12, 13.
   - Replace the Proposals list's 12 inline-styled filter-chip links with a single
     data-driven `.filter-chip`/`.filter-chip.active` component, fixing the "All" chip's
     missing active state as part of the same change.
   - Move "Delete" out of the top nav row and "Undo Approval" out of the status-badge
     paragraph on the proposal detail page into one clearly separated actions area, so
     destructive/admin actions are never adjacent to plain navigation.
   - Standardize "in favor" on one color (matching the existing `.vote-approve` cyan)
     everywhere a vote count is shown, instead of cyan in one place and green in another.
   - Reorder the Polls page's three cards so "Vote via web" leads, and give its button
     the same `.vote-btn` visual weight as proposal voting, so the two voting flows read
     as the same product.
   - Add a `title=""` attribute to truncated proposal titles so the full text is
     recoverable without opening the detail page.
3. **Budget graph and visualization improvements.** Closes audit items 14, 15, 16, 17,
   18, 19, 20 — the sprint's namesake ask.
   - Self-host Chart.js (vendor it under `static/`) instead of loading it from a public
     CDN at render time.
   - Add a date-range control (e.g. last 30/90/365 days / all) to the budget chart so it
     stays legible as history grows, rather than always rendering the full history.
   - Add a restated "current balance" headline at the top of the budget page itself,
     so it doesn't require reading the end of the line chart.
   - Reconcile the two currently-disconnected filter UIs: either wire the calendar
     legend buttons to also toggle the matching chart dataset, or make clear visually
     that they're two separate controls.
   - Give each poll option's result bar a distinct color instead of the same gradient
     for every option.
   - Add thousands separators to currency formatting app-wide.
4. **Member feedback / bug reports / suggestions.** New feature (not from the UX audit),
   scoped per `IDEAS.md`'s "Member feedback / bug reports / suggestions (2026-08-27)".
   - New `feedback` table (`member_id`, `source`, `category`, `message`, `status`,
     `created_at`, `resolved_at`, `resolved_by`) via the standard migration pattern.
   - `app/services/feedback_service.py` (submit/list/update-status), reason-coded
     `event=feedback_submitted`/`event=feedback_status_changed` logging matching the
     established style.
   - REST: `POST /api/feedback` (any member), `GET /api/feedback` (admin, paginated,
     filterable), `PATCH /api/feedback/<id>` (admin, status transitions).
   - MCP: new `create_feedback` tool so the Telegram assistant can store feedback when
     a member asks it to. First member-writable (non-admin-only) mutating tool in the
     MCP surface — needs a new `MEMBER_WRITABLE_TOOLS` category in
     `telegram_agent.py` distinct from the existing admin-only `MUTATING_TOOLS`, scoped
     so a member can only attribute feedback to their own `member_id`. Whether it
     should go through the existing `/confirm` flow is an open call to make during
     implementation (leaning no — see `IDEAS.md` for reasoning); flag for a second
     opinion since it would be the first mutating tool to deliberately skip that
     pattern.
   - Admin panel: new "Feedback" section in `admin.html` listing submissions with
     status/category badges (reusing `.status`/`status-*` classes, not one-off inline
     colors) and a mark-reviewed/resolved action.
   - First slice explicitly excludes admin notifications, a member-facing status view,
     and attachments — see `IDEAS.md` for the full non-goals list.

### Explicitly deferred (with reasoning, not just left off)
- **Public MCP application boundary (`IDEAS.md` item 4, P1)** — real architectural value,
  previously flagged as the leading Sprint 7 candidate, but the user redirected Sprint 7
  to UX/UI. Now the leading candidate for Sprint 8.
- **`admin.html` information-architecture restructuring (audit item 26)** — splitting a
  ~780-line, 14-section page into tabs/anchors is a bigger, higher-risk rewrite than
  anything else scoped here and doesn't block the goals above. Good candidate for its
  own sprint once the shared confirm-modal/component work in Goal 1 gives it something
  to build on.
- **Proposals list search/sort (audit item 27)** — real gap, but additive rather than a
  fix to something actively wrong, and secondary to the filter-chip cleanup in Goal 2.
  Natural follow-up once Goal 2's `.filter-chip` component exists.
- **Design-token system / full component library (Design Track item C)** — the
  foundational, app-wide version of what Goal 2 does narrowly for filter chips and vote
  buttons. Revisit once a couple of concrete passes (this sprint) show which patterns
  actually repeat enough to warrant tokens.
- **Personas, journey mapping, admin/settings IA relabeling (Design Track items A, B)** —
  product-definition exercises, not code changes; useful before a larger IA rewrite
  (see `admin.html` deferral above) but not blocking this sprint's concrete fixes.
- **Two hardcoded English admin headers (audit item 25)** — trivial one-line `|lang`
  fixes; will be picked up opportunistically while touching `admin.html` for Goal 1's
  modal work rather than tracked as a standalone goal.

### Exit criteria
- Every destructive/state-changing action in the member-facing UI (not just admin) uses
  the same styled, accessible confirmation modal and the same POST-based mechanics.
- Proposal and poll voting use visually consistent buttons and colors; the Proposals
  filter row has no dead/ambiguous active-state gaps.
- The budget chart doesn't depend on a public CDN at render time, offers a date-range
  control, and the page restates the current balance without requiring the chart to be
  read.
- A member can submit feedback from the web app and from the Telegram assistant; every
  submission is visible and triageable (status + category) from the admin panel; REST
  and MCP stay convergent on the same `feedback_service` rather than duplicating
  validation.

### Progress
- ✅ Goal 2's proposal/poll hierarchy slice is complete: proposal filters now use one
  data-driven filter-chip component with an active state (including “All”), truncated
  titles expose their full value, in-favor counts use the shared cyan vote color, and
  poll voting now leads the card row with the same visual weight as proposal voting.
- ✅ Goal 3's poll-results color item is complete: options cycle through five distinct,
  accessible result colors rather than sharing a single gradient.
- ✅ Goal 3 is now complete: Chart.js 4.5.1 is self-hosted with its MIT license, the
  chart defaults to a readable 90-day window with 30/365/all-time controls, and the
  page leads with the current balance. Chart-range and activity-table controls now have
  separate headings, while a shared `currency` template filter adds thousands separators
  consistently across every member-facing monetary amount.
- ✅ Goal 1 is complete: the admin confirmation dialog is now a shared, translated
  component included by the base layout and used by every member-facing destructive
  action. It has dialog semantics, focus return/trapping, outside-click and Escape
  dismissal; proposal delete/undo actions live in a separate actions area; undo and
  vote withdrawal are POST-only; settings menus open on focus as well as hover; and
  app-wide pinch-to-zoom is no longer disabled.
- ✅ Goal 4 is complete: members can submit categorized feedback from Settings or the
  REST API, the Telegram assistant exposes a member-scoped `create_feedback` tool
  without an unnecessary confirmation round-trip, and admins can list/filter/update
  feedback through REST or triage it from a dedicated Admin tab. All transports share
  `feedback_service` validation, persistence, reason codes, and structured audit logs.

**Status:** ✅ Complete (2026-08-27).

---

## Sprint 8 (Completed 2026-08-27) — Public MCP Application Boundary

### Goal
Replace the Telegram assistant's dependence on MCP server internals with a public tool
registry/application boundary, keeping transport authentication outside application
logic and denying new Telegram tools until their actor policy is explicit.

### Progress
- ✅ First slice: promoted MCP tool discovery to the public `tool_definitions()` API and
  introduced `mcp_tool_registry` as the single source of Telegram actor policy. Member
  reads, admin reads, member writes, and confirmed admin writes are classified beside
  the registry; unclassified tools are denied by default. The registry also owns removal
  of server-attributed member/creator fields before schemas are shown to the model.
- ✅ Second slice: added the transport-neutral `mcp_application.execute_tool()` boundary.
  JSON-RPC authenticates first and enters as the system actor; Telegram enters with an
  explicit member/admin actor and no longer constructs an authenticated JSON-RPC request
  or reads the MCP API key. The application layer denies unclassified tools, enforces
  admin policies, and overwrites member/creator attribution before dispatch.

**Status:** ✅ Complete (2026-08-27).

---

## Sprint 9 (Active 2026-08-29) — Telegram Proposal Resource Sharing

### Goal
Let linked members ask naturally for any proposal and receive usable, unambiguous links
to its ManaVote detail page and uploaded image without confusing those resources with
the proposal's external vendor/reference URL.

### Progress
- ✅ `list_proposals` now returns `proposal_url` and `image_url`, derived from the public
  Base URL configured in Admin → Telegram Configuration. Missing configuration or images
  produce explicit `null` fields rather than malformed relative links.
- ✅ Uploaded-image filenames are URL-encoded before they are exposed.
- ✅ The Telegram tool prompt and sample configuration tell the model to include these
  resource links when available and preserve the separate external reference `url`.
- ✅ `list_proposals` accepts an exact positive `proposal_id`, allowing natural chat to
  retrieve an older or otherwise non-default-page proposal by ID.
- ✅ MCP contract and Telegram prompt regression tests cover generated, absent, and
  filename-encoded URLs plus exact-ID validation and filtering.
- ✅ The end-to-end webhook contract now requests a specific proposal through the model,
  executes the real MCP application path, and verifies Telegram receives both public
  resource URLs while the external reference URL remains distinct.

- ✅ Admin → Telegram Configuration now displays a localized warning when the public
  Base URL is missing, explaining that Telegram/MCP proposal and image links require it.
- ✅ Base URL updates now require a credential-free HTTPS URL, reject ambiguous query or
  fragment components, and support explicitly clearing the setting without leaving a
  stale URL active or attempting an invalid webhook synchronization.
- ✅ When an assistant answer references an MCP-provided `image_url`, Telegram now sends
  the resource with `sendPhoto` in the originating private chat or forum thread, while
  retaining the clickable image URL in the textual answer.

### Exit criteria
- A linked member can request a proposal by ID in Telegram natural language and receive
  its public detail URL plus image URL when an image exists.
- External reference URLs remain clearly distinct from ManaVote-owned resource URLs.
- Missing Base URL configuration is visible to operators and never creates broken links.

**Status:** ✅ Complete (2026-08-29).
