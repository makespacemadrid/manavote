# IDEAS — Forward Roadmap

Last updated: 2026-08-26

This document captures **forward-looking** product and engineering initiatives only.
Execution sequencing and status tracking belong in [`SPRINTS.md`](SPRINTS.md).

---

## Planning Principles

Planning/development principles and guardrails live in [`STYLE.md`](STYLE.md).

---

## Strategic Outcomes (Next Quarter)

1. Route layer becomes thin and modular (Blueprint-oriented, low coupling).
2. Startup becomes deterministic and auditable (single orchestrator + explicit checks).
3. API behavior becomes contract-driven (stable schemas + standardized errors).
4. Operations become diagnosable (structured events, participation metrics, key counters, backup confidence).

---

## Workstreams & Backlog

## Recent audit notes (2026-08-25)

Audit scope focused on the REST/MCP proposal-list and user-statistics contracts, while
rechecking the previously audited Telegram-link parity paths.

### Confirmed strengths
- REST and MCP member-link diagnostics now share one canonical SQL classification helper (`app/services/telegram_link_diagnostics.py`), reducing drift risk.
- REST/MCP parity tests now cover both success shape and invalid pagination bounds for Telegram member-link listing.
- Proposal age filtering has an explicit shared contract (`recent|old`, 30-day boundary) across REST and MCP.
- User participation statistics are available through REST and MCP, backed by one canonical query in `app/services/user_statistics.py`.
- Parity tests cover the user-statistics response shape and invalid pagination bounds.

### Follow-up gaps to prioritize
1. **Route exception granularity (P0)**
   - Several route handlers still use broad `except Exception` blocks and generic failure messages.
   - Introduce typed exceptions + reason-code mapping for predictable operator diagnostics.

2. **MCP extraction boundary (P1)**
   - User statistics and Telegram link classification now have shared boundaries, but proposal listing, voting-setting writes, and create operations remain embedded in `app/mcp_server.py`.
   - Extract one use case at a time behind service/repository interfaces shared with REST; avoid a broad rewrite.

3. **Statistics scale and semantics (P1)**
   - The user-statistics query uses correlated count subqueries and has no total-row metadata for pagination.
   - Capture `EXPLAIN QUERY PLAN` results with production-like data, add indexes only where evidence supports them, and define whether future clients need `total` in addition to page `count`.
   - Decide whether statistics remain lifetime-only or gain explicit `from`/`to` time windows; do not silently change existing lifetime semantics.
   - Progress (2026-08-26): REST and MCP statistics now return explicit matching `total`
     alongside page `count`; lifetime semantics remain unchanged and documented.

4. **Error-contract matrix expansion (P1)**
   - Extend parity coverage beyond voting, Telegram listing, proposal age filtering, and user statistics:
     - proposal create/update validation edges,
     - poll creation bounds,
     - pagination/type errors across list endpoints.
   - Progress (2026-08-27): added REST/MCP parity tests for `create_proposal` (missing
     fields, non-positive amount, unknown/non-positive `created_by`, invalid
     `basic_supplies`, success shape) and `create_poll` (question/option bounds, success
     shape). This surfaced and fixed two real drifts rather than just documenting them:
     REST silently coerced any truthy `basic_supplies` value (including the JSON string
     `"false"`, which is truthy in Python) instead of validating it like MCP already did;
     and MCP's `create_proposal` uniquely treated a non-positive `created_by` as an
     invalid-params error while REST and MCP's own `create_poll` both treat it as
     not-found. Proposal *update* has no MCP equivalent tool, so its validation edges
     still only have REST-side coverage.
   - Progress (2026-08-27): closed the pagination/type-errors item. Added REST/MCP parity
     tests for `list_proposals` pagination (out-of-range limit, non-integer limit, negative
     offset) — REST already validated these correctly, this was a test-coverage gap only.
     Found and fixed a real drift for polls: MCP's `list_polls` tool already supported
     `limit`/`offset` (bounds 1-200, same as `list_proposals`), but REST's `GET /api/polls`
     had no pagination at all — a hardcoded `LIMIT 100` with no query params or validation.
     Added `limit`/`offset` support to `GET /api/polls` using the same
     `parse_pagination_params` helper and error codes (`invalid_limit`, `invalid_offset`,
     `limit_out_of_range`, `offset_out_of_range`) as the other three REST list endpoints,
     and added `count`/`limit`/`offset` to its response shape to match. Documented in
     `APIDOC.md`. Added parity tests covering the new pagination working (limit/offset
     honored, response shape matches MCP's) and its rejection paths (out-of-range limit,
     non-integer offset). Full suite: 530 passed, zero regressions.

5. **Observability completion for Telegram lifecycle (P2)**
   - Add reason-coded audit events for link/unlink operations and blocked votes by policy mode.
   - Expose `last_linked_at`/`last_unlinked_at` metadata for admin diagnostics.
   - Progress (2026-08-27): `members.last_linked_at`/`last_unlinked_at` are now set on
     every link (`/link` command or an OIDC login whose claims carry a Telegram identity)
     and unlink (admin or member self-service), and exposed on both
     `GET /api/members/telegram` and the `list_member_telegram_links` MCP tool. Blocked
     votes by policy mode still need reason-coded audit events.

6. **Statistics privacy and authorization review (P2)**
   - User statistics expose member email addresses to API/MCP administrators.
   - Document the operator need for that field, consider an `include_email` opt-in defaulting to false, and add an authorization regression test before expanding the statistics surface.
   - Progress (2026-08-26): REST and MCP now omit email by default and require an
     explicit administrator-only `include_email` opt-in. Parity and invalid-value tests
     cover both transports, and the canonical field/count semantics are documented.

## Telegram natural-language + MCP audit (2026-08-26)

Audit scope covered the complete assistant branch: webhook admission, database-backed
identity, model/tool orchestration, MCP authorization, mutation confirmation, worker
backpressure, Telegram transport, retry behavior, documentation, and focused tests.

### Confirmed strengths
- Telegram identity and administrator status are read from `members.telegram_user_id`
  for every natural-language request, so link/unlink and role changes do not require a restart.
- Ordinary members receive only proposal, budget, and voting-setting tools; sensitive
  statistics, Telegram-link records, and all mutations remain administrator-only.
- Mutations require a separate `/confirm`, are isolated by chat and user, expire after
  a bounded TTL, and can be discarded with `/cancel` or `/reset`.
- Model work has bounded active/pending capacity, long answers respect Telegram limits,
  and users receive a temporary thinking status while work runs.
- Telegram webhook retries are deduplicated before commands, votes, model calls, and
  MCP actions; deduplication memory is bounded.
- Focused tests cover the agent, access lookup, executor, webhook helpers, and Telegram
  client. Setup, architecture, operations, and test commands are documented.
- Luis Rivera and `ocabra_telegram` are credited in the README, API documentation, and
  agent module.

### Production blockers and follow-up priorities

1. **Secret-bearing MCP tools and confirmation output (mitigated 2026-08-26)**
   - `create_member` accepts a password, and the current generic confirmation text can
     echo every tool argument back into Telegram. Do not expose password-bearing tools
     until the assistant has per-field secret classification and redaction.
   - Prefer excluding `create_member` from Telegram entirely, or replace password input
     with a one-time server-generated enrollment flow.
   - Add regression tests proving secrets never enter prompts, history, logs, confirmation
     messages, MCP error text, or Telegram responses.
   - Progress: `create_member` is excluded from the Telegram tool registry for every
     actor, including administrators. The registry is now an explicit allowlist, so new
     MCP tools are denied by default. Confirmation display arguments also redact nested
     password, secret, token, and API-key fields. Regression tests cover schema,
     direct-call, and confirmation boundaries; broader log/history controls remain
     follow-up work.

2. **Shared state for multi-worker/restart safety (P0)** — ✅ closed (2026-08-27).
   - Conversation history, pending confirmations, update deduplication, and queue state
     are process-local. Multiple WSGI workers can route `/confirm` to a process that does
     not own the pending action; restarts lose confirmations and retry memory.
   - Either document/enforce a single application worker for the initial release or move
     pending actions and idempotency keys to SQLite/Redis with expiry and atomic consume.
   - Treat mutation idempotency as a database/MCP invariant, not only a webhook cache.
   - Progress (2026-08-26): webhook update IDs and pending confirmations now use SQLite,
     are shared by all application workers, and survive restarts. Confirmations are
     atomically consumed before execution.
   - Progress (2026-08-27): conversation history now uses the same SQLite-backed pattern
     (`telegram_conversation_history`, `configure_history_store`), bounded to the last
     `MAX_HISTORY_MESSAGES` (12) turns per chat/user and shared across workers.
   - **Decision (2026-08-27)**: the one remaining piece — the bounded model-request
     queue's in-process worker pool — stays process-local by design; it does not move to
     SQLite/Redis. Reasoning:
     - Every piece of state where cross-worker visibility is a *correctness* requirement
       (a `/confirm` reply must find the pending action a different worker created; a
       retried webhook must not be reprocessed; conversation history must be consistent
       regardless of which worker answers) is now durable and shared, per the two
       progress notes above. The queue's job is different in kind: it only limits how
       many model calls run concurrently *within one process*, to avoid overloading the
       downstream LLM API. It doesn't need cross-worker visibility to do that correctly —
       each process independently staying within its own 4 active / 32 pending bound is
       sufficient for that purpose.
     - The actual residual risk was never "an in-flight job is invisible to other
       workers" — it was "if the process holding a job crashes mid-flight, that one reply
       is silently lost, with nothing logged and no signal to the user or an operator."
       That's a real gap, but a narrow one: the user's message was already deduplicated
       (marked consumed) so it will never be retried, and it costs the user one missed
       chat reply, recoverable by asking again. Nothing that requires durability — votes,
       proposal mutations, `/confirm` itself — depends on this in-memory queue; those all
       already flow through the SQLite-backed paths above.
     - A genuine fix for that narrow gap (a persistent job queue with claim/lease
       semantics, retry/backoff, and safe-replay handling for a job that was mid-flight
       when a process died) is real infrastructure work, and disproportionate to what it
       buys for an app at this scale (a small community makerspace tool, not a
       high-throughput service) — and it would add a new dependency (Redis, or a
       hand-rolled SQLite lease system) this app doesn't otherwise need. "A single
       dedicated assistant worker" (the other option floated in the prior note) doesn't
       actually eliminate the risk either — that one worker can still crash mid-job — so
       it wasn't pursued as a fix for this specific gap.
     - What was fixed instead, because it's cheap, safe, and closes the part of the gap
       that actually matters — silence: `_answer_and_send` in `app/web/routes/telegram_routes.py`
       previously had no catch-all around reply generation or delivery, so
       `concurrent.futures` would silently drop any exception outside the narrow
       `(requests.RequestException, RuntimeError, KeyError, IndexError, ValueError)` tuple
       `_natural_language_reply` already handled — including any failure in
       `client.send_long_message(...)` itself, or in the `on_proposal_created` callback.
       Wrapped every stage (reply generation, delivery, thinking-message cleanup) in its
       own try/except that logs via `app.logger.exception(...)` with chat/member context
       and, where possible, still sends the user a graceful fallback message instead of
       leaving them with a deleted "🤔 Thinking…" message and nothing else. Regression
       test added: `test_unexpected_reply_error_is_logged_and_user_gets_a_graceful_message`
       in `tests/test_telegram_natural_language_webhook.py`, which forces an exception type
       outside that tuple and asserts it's both logged and gracefully answered rather than
       silently dropped.
     - Operational note for future deployment changes: the model-request concurrency cap
       (4 active / 32 pending) is enforced *per process*. Running N worker processes
       multiplies the effective global cap by N. That's fine at this app's current scale;
       revisit if the deployment ever moves to many workers or the assistant sees load
       that makes per-process-only bounding matter.

3. **End-to-end natural-language webhook contract (P0)** — ✅ delivered (2026-08-27)
   - Existing functional webhook tests exercise deterministic commands and callbacks,
     while model/Telegram lifecycle pieces are primarily unit-tested.
   - Add a Flask-level test covering linked and unlinked senders, thinking-message create
     and delete, tool call, final chunk delivery, duplicate `update_id`, and queue-full UX.
   - Add an administrator test spanning proposed mutation → `/confirm` → one MCP write,
     including role removal between proposal and confirmation.
   - `tests/test_telegram_natural_language_webhook.py` now drives the real
     `POST /telegram/webhook/<secret>` route end-to-end (mocking only the outbound
     Telegram HTTP client and the OpenAI-compatible model response) covering every item
     above. Building it surfaced a real test-infrastructure gotcha worth remembering: the
     update-ID deduplicator persists to the shared session SQLite file by design, so
     fixed literal `update_id`/`telegram_user_id` values collide across separate test
     runs against that file — the test generates fresh ones every run.

4. **Public MCP application boundary (P1)**
   - The assistant currently consumes the private `_tool_definitions()` helper and calls
     the JSON-RPC request handler in-process with the server API key.
   - Introduce a public MCP tool registry/application service that both transports and
     the Telegram adapter call. Keep authentication at transport boundaries and actor
     authorization in the application layer.
   - Move per-tool Telegram policy next to tool metadata so new MCP tools are denied by
     default until explicitly classified as member-read, admin-read, or confirmed-write.

5. **Background-job observability and lifecycle (P1)**
   - Attach `update_id`, chat ID, actor member ID, tool name, queue wait, model latency,
     MCP latency, delivery result, and stable reason codes to structured logs.
   - Observe completed futures so unexpected worker exceptions cannot remain silent.
   - Add graceful executor shutdown and counters for active, queued, rejected, failed,
     cancelled, and completed requests without logging prompts or secrets.

6. **Fair-use limits and cancellation (P1)**
   - The global bounded queue protects memory but one linked user can consume all slots.
   - Add per-user concurrency/rate limits, maximum input/history token budgets, and a
     clear cooldown response. Consider queue fairness across chats.
   - Let `/cancel` cancel queued/running model work as well as pending mutations where
     the HTTP client and executor can do so safely.

7. **Confirmation integrity and auditability (P1)**
   - Store an immutable/deep-copied action envelope with actor member ID, tool schema
     version, redacted display arguments, expiry, and a digest of execution arguments.
   - Revalidate linkage, administrator role, tool availability, and arguments at confirm
     time, then atomically consume the action before executing it.
   - Emit a reason-coded audit record for proposed, cancelled, expired, rejected, failed,
     and completed mutations.
   - Progress (2026-08-26): pending actions are claimed (popped) before validation and
     execution, so two workers can no longer race the same mutation, and `/confirm`
     already revalidates administrator role and actor-linkage drift. Tool-schema
     versioning, an execution-argument digest, and reason-coded audit records for
     proposed/cancelled/expired/rejected/failed/completed mutations remain open.

8. **Conversation quality and operator controls (P2)**
   - Add explicit token budgeting and model-context truncation rather than message-count
     truncation alone; publish model/timeout/queue health in admin diagnostics.
   - Evaluate Telegram `sendChatAction(typing)` or editing the temporary status message
     for smoother UX, with localization for assistant-owned deterministic messages.
   - Add opt-in, privacy-reviewed durable history only if a concrete member workflow
     requires it; keep the default ephemeral and document retention clearly.

## Telegram forum-topic routing audit (2026-08-26)

Audit scope covered the most recent commits hardening Telegram group address
matching and forum-topic routing: `is_natural_language_message`,
`is_configured_forum_topic`, thread-aware `TelegramClient` replies, and the
`/confirm@botname` / `/cancel@botname` normalization added on top of the
natural-language/MCP audit above.

### Confirmed strengths
- Reply-to-topic-root messages that only carry `message_thread_id` on
  `reply_to_message` (rather than on the outer message) are now attributed to
  their topic correctly, keeping both assistant routing and outgoing replies
  anchored to the right thread.
- Deterministic command replies (`/link`, `/pvote`, `/vote`, `/help`, `/reset`)
  and natural-language replies both carry `message_thread_id` and
  `reply_parameters` back to Telegram, so forum-topic conversations no longer
  leak into the supergroup's General topic.
- `/confirm@botname` and `/cancel@botname` (Telegram's mandatory group-chat
  command syntax) are normalized before comparison, so confirmations are no
  longer silently dropped when an admin confirms from a group or forum topic.
- A configured assistant forum topic (`TELEGRAM_CHAT_ID` + `TELEGRAM_THREAD_ID`)
  is treated as an implicit conversation without requiring an `@mention` on
  every message, and the routing/reply behavior is exercised by focused unit
  tests (`tests/unit/test_telegram_webhook_helpers.py`, `tests/test_telegram_client.py`).

### Follow-up gaps to prioritize

1. **Unconfigured bot-username group matching is overly permissive (P2)**
   - `is_natural_language_message` only exact-matches an `@mention` or
     `bot_command` entity against `TELEGRAM_BOT_USERNAME`; when that variable is
     unset (still the `sample.env` default) it accepts any `mention`/`bot_command`
     entity as a match. With Telegram privacy mode disabled, the webhook receives
     every group message, so an unconfigured bot username makes the assistant
     respond to messages that mention a different user or invoke a different
     bot's command in the same chat.
   - Docs already recommend setting `TELEGRAM_BOT_USERNAME`; add a startup check
     that warns (or refuses to enable non-forum-topic group handling) when a
     Telegram group integration is configured without it, so the permissive
     default cannot ship unnoticed.

2. **No operator visibility into forum-topic/mention routing decisions (P2)**
   - Neither the addressed-message match nor the configured-forum-topic match
     emits a structured log/event, so misrouted or unexpectedly silent group
     messages are hard to diagnose in production.
   - Once WS-D's structured logging lands, attach a reason code (`private`,
     `mentioned`, `reply_to_bot`, `forum_topic`, `unaddressed`) to each webhook
     decision.

## Docs audit findings requiring a product decision (2026-08-26)

A full audit of `docs/*.md` against the current codebase (see the four commits fixing
`APIDOC.md`, `SPEC.md`, `QUICKSTART.md`, and `TESTING.md`) surfaced one behavior that
docs previously described incorrectly and that deserves an explicit decision rather than
a silent doc fix:

1. **OIDC/SSO login silently attaches to an existing password account by email match (P1)**
   - `_upsert_oidc_member` (`app/web/routes/auth_routes.py`) looks up a member with
     `oidc_sub IS NULL` and a matching `email` (case-insensitive) whenever no member is
     yet linked to the incoming `sub`, and attaches the SSO identity to that account —
     including syncing `is_admin` from the token's `groups` claim. `docs/QUICKSTART.md`
     previously claimed the opposite ("Manavote never silently attaches an SSO identity
     to an existing password account"); the docs now describe the real behavior.
   - This is likely intentional (letting an existing password-account member adopt SSO
     without creating a duplicate account), but it means a member's local `email` field
     — which is not itself verified — controls which account a future Keycloak login
     takes over, including a potential admin-role grant. Confirm this is the intended
     trust model, and consider requiring the email match to also come from a currently
     `oidc_sub IS NULL` account created through a trusted path (not self-service email
     edits) before relying on it for admin accounts.

## WS-A — Architecture Refactor (P0)

### A1. Decompose route concerns
- Split route responsibilities into focused modules (`auth`, `proposal`, `poll`, `admin`, `api`).
- Move shared orchestration helpers into route-helper or service layers.
- Register route modules consistently through app setup.
- Progress (2026-08-27): the `/admin` handler (627 lines), all 11 proposal-lifecycle
  handlers, `proposals()` (the main listing page, ~155 lines), and `telegram_webhook`
  (~180 lines, into a new `telegram_routes.py` blueprint) all moved out of
  `main_routes.py` into their real blueprint homes, cutting `main_routes.py` from 2368
  to 873 lines (-63.1%). Route decomposition itself is now close to done; what remains
  in `main_routes.py` is almost entirely the shared helper layer (`get_db`,
  threshold/vote-mode calculations, Telegram command processors, `record_proposal_vote`,
  ~30 functions) plus small compatibility shims — moving the helpers into
  `app/services/`/`app/repositories/` is A2's service/repository boundary work, not A1's
  route decomposition.

### A2. Complete service/repository boundary
- Route handlers call service entry points only.
- Repositories own query composition and persistence concerns.
- Critical domain operations gain direct service-level test coverage.
- Progress (2026-08-27): extracted the poll/proposal vote-mode policy logic (7 functions —
  `get_poll_vote_mode`, `is_web_poll_voting_enabled`, `is_telegram_poll_voting_enabled`,
  `require_linked_telegram_for_votes`, `get_proposal_vote_mode`,
  `is_web_proposal_voting_enabled`, `can_record_proposal_vote`) plus
  `is_registration_enabled` into a new `app/services/voting_mode_service.py`. Each function
  now takes `get_setting_value` as an explicit parameter instead of reaching for a module
  global, so the policy is directly unit-testable without a DB or Flask context (6 new
  tests in `tests/unit/test_services.py`, no mocking needed). `main_routes.py` keeps
  one-line wrapper functions at the original names — every other blueprint module still
  reaches these via `legacy.X` (per A1's alias pattern) and the ~15 existing tests that
  `unittest.mock.patch("app.web.routes.main_routes.X", ...)` these names keep working
  unchanged, since patching a module attribute doesn't care what it currently points to.
  Verified with the full suite: 492 passed (486 + 6 new), same 4 pre-existing/environmental
  failures, zero regressions.
- Progress (2026-08-27, second slice): extracted the poll-close/results helpers
  (`close_expired_polls`, `build_poll_results_message`) into a new
  `app/services/poll_service.py`. These were already shaped like service functions (pure
  given a `conn`, no module-global reads), so the move is a straight relocation with no
  signature change. `main_routes.py` keeps one-line wrappers at the original names for the
  same `legacy.X`/patch-compatibility reasons as the first slice. Retargeted
  `tests/unit/test_poll_closing.py`'s three tests to call `poll_service.X` directly instead
  of `main_routes.X`, since they already built an isolated in-memory DB and never depended
  on Flask/app internals — a better fit for the new module boundary and no loss of
  coverage. Full suite: 492 passed, same 4 pre-existing failures, zero regressions.
  Remaining in `main_routes.py`'s shared helper layer: `get_db` and its settings/budget
  read wrappers (already thin repository wrappers — see `SettingsRepository`), the
  Telegram command processors (`process_telegram_vote_command`,
  `process_telegram_proposal_vote_command`, `process_telegram_vote_callback`,
  `process_telegram_link_command`), `record_proposal_vote`/`log_proposal_vote_event`, and
  the Telegram messaging/webhook-sync helpers (`send_telegram_message`,
  `sync_telegram_webhook*`) — all still call through module globals so future slices
  should follow the same parameter-injection pattern rather than importing `main_routes`
  internals directly.
- Progress (2026-08-27, third slice): extracted the deterministic Telegram vote-command
  processors — `process_telegram_vote_command`, `process_telegram_vote_callback`, and
  `process_telegram_proposal_vote_command` (~150 lines of command parsing, member lookup,
  and vote-recording logic; not the natural-language assistant path) — into a new
  `app/services/telegram_command_service.py`. Each function takes `get_db`,
  `get_setting_value`, `send_telegram_message`, and/or `record_proposal_vote` as explicit
  parameters, so it calls `poll_service`/`voting_mode_service` directly rather than through
  `main_routes`, and is directly testable with a stub settings getter and a throwaway
  sqlite file — no Flask, no monkeypatching (12 new tests in
  `tests/unit/test_telegram_command_service.py`, covering disabled-channel rejection,
  malformed commands, linked vs. unlinked-but-permitted Telegram voters, the
  `telegram_require_linked_vote` gate, proposal-vote success/rejection, and both callback
  dispatch branches). `main_routes.py` keeps one-line wrappers at the original names, same
  `legacy.X`/patch-compatibility reasoning as the prior two slices — nothing in the test
  suite patches `close_expired_polls`/`build_poll_results_message`/`send_telegram_message`
  *while exercising these specific command processors*, so bypassing `main_routes` inside
  the new service module for the already-relocated `poll_service` calls is safe (confirmed
  by grep before making the change). Deliberately left `process_telegram_link_command` in
  `main_routes.py` — it's already a thin adapter over `process_link_command` (an existing
  service) plus one audit-log call, so moving it would trade one call site for four
  injected parameters with no real logic gained. Dropped the now-dead `json` import from
  `main_routes.py` (its only remaining use was inside the moved commands). Full suite: 504
  passed (492 + 12 new), same 4 pre-existing/environmental failures, zero regressions.
  Remaining A2 scope: `get_db`/settings-budget read wrappers, `record_proposal_vote`/
  `log_proposal_vote_event`, `process_telegram_link_command`, and the Telegram messaging/
  webhook-sync helpers (`send_telegram_message`, `sync_telegram_webhook*`).

### Fixed: the 4 tests repeatedly labeled "pre-existing/environmental" all session
Every progress note above (and earlier ones) reported "same 4 pre-existing/environmental
failures, zero regressions" without root-causing them. Investigated properly (2026-08-27)
and fixed all four — none were flaky or environmental in the "can't be fixed" sense:
- **`test_language.py::TestProposalStatusTags`** (3 tests: approved/rejected/over-budget
  lowercase status tags) — two real bugs, not test flakiness:
  1. `templates/proposals.html`'s status badges for `approved` and `over_budget` used
     inline `style=` only, never the `status-approved`/`status-over-budget` CSS classes
     that `static/react/style.css` already defines for them (and there was no badge
     branch for `rejected` at all — a real, if minor, UI gap, since `rejected` is a valid
     proposal status per `app/domain/enums.py` and is set by the admin reject action).
     Fixed the template to add the missing classes and the missing `rejected` branch
     (kept the existing inline colors for `approved`/`purchased` to avoid an unreviewed
     visual change; `rejected`/`over_budget` now render via the CSS class alone, matching
     the `active` badge's existing pattern). Added the missing `"rejected"`/`"rechazado"`
     translation key pair.
  2. Even with the template fixed, the tests could still fail depending on what other
     test files happened to run first: `GET /proposals` with no `filter` query param (and
     the "All" filter button, which linked to `url_for('proposals')` with no filter at
     all) only ever shows `status = 'active'` proposals — so a run where no earlier test
     left an approved/rejected/over-budget proposal behind in the shared session DB would
     fail regardless of the template fix. Fixed the "All" button to link to
     `filter=all` so it actually reaches the unrestricted "show every status" query
     branch (it was silently behaving identically to "Active" before — a second small
     real bug). Fixed the test class to seed one proposal per status itself in
     `setUpClass`/clean up in `tearDownClass`, and to request the correct filter for
     each status (`filter=approved`, `filter=over_budget`, `filter=all` for rejected)
     instead of depending on ambient DB state left by unrelated tests.
- **`test_production_config.py::test_init_db_fails_without_bootstrap_password_in_production`**
  (plus 3 more `test_app_setup_*` tests in the same file that were being silently excluded
  all session via `-k "not test_app_setup_"` rather than fixed) — all four spawn a
  subprocess via bare `"python"` instead of `sys.executable`. In this sandbox, `python`/
  `python3` resolves to a Python 3.11 interpreter, but the only `_cffi_backend` shared
  object on the system path is built for cpython-312 — so any subprocess that imports
  `cryptography.x509` (via `authlib`, pulled in by `app.extensions`) hits
  `ModuleNotFoundError: No module named '_cffi_backend'`, which PyO3 turns into a Rust
  panic. Confirmed by reproducing it directly (`python3 -c "import cryptography.x509"`)
  independent of any test or app code. Fixed by using `sys.executable` in all four
  subprocess calls, guaranteeing the subprocess runs with whatever interpreter is
  actually running pytest (the `/tmp/testvenv` used throughout this session, where
  `cryptography` is a matched pip install) rather than gambling on `PATH`.
- Full suite now passes clean with no exclusions: **511 passed, 0 failed** (previously
  508 collected with 3 deselected + 4 failing = 511 either way — nothing was hidden or
  skipped, just broken). `pytest -q tests/` is the correct full-suite command going
  forward; the `-k "not test_app_setup_"` qualifier used throughout this session's prior
  runs is no longer needed and shouldn't be reintroduced.

---

## WS-B — Startup Reliability (P0)

### B1. Single startup orchestrator
Proposed startup lifecycle:
1. config load + validation
2. DB connect + migrations
3. settings/bootstrap checks
4. integrations (Telegram, scheduler)
5. readiness summary

### B2. Exception policy + startup report
- Replace broad catch-all behavior with targeted exception classes.
- Define clear severity levels (`fatal`, `degraded`) and actions.
- Emit one structured startup summary event per boot.

---

## WS-C — API & Domain Consistency (P1)

### C1. Standard error envelope
- Use one failure shape across API endpoints:

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
- Validate inbound payloads and guarantee outbound response shape.
- Publish one canonical field dictionary for REST/MCP user statistics, including count semantics and nullable fields.
- Add compatibility tests that fail on accidental field removal or type changes.

### C3. Proposal lifecycle state machine
- Centralize legal transitions.
- Return stable error codes for illegal transitions.

### C4. Query/index optimization pass
- Add indexes for high-frequency filters/lookups.
- Capture before/after query plans for key endpoints.
- Benchmark proposal age filters and user-statistics aggregation with production-like row counts before choosing indexes or query rewrites.

### C5. Participation analytics evolution
- Preserve the current lifetime, per-user statistics response as the stable baseline.
- Evaluate optional date windows, explicit sort keys, and aggregate totals from concrete admin workflows.
- Keep email/identity fields minimal and require administrator authentication for every analytics surface.

---

## WS-D — Security & Operations (P2)

### D1. Credential hardening
- Replace static non-prod bootstrap fallback with one-time generated secret flow.
- Add safe API key rotation support (`active` + `next`).

### D2. Structured logs + telemetry
- Standardize JSON log fields (`request_id`, `actor_id`, `endpoint`, `status`, `latency_ms`, `reason_code`).
- Add counters/timers for throughput, error rates, and latency.

### D3. Backup validation
- Add periodic backup recency/readability verification.
- Emit health signals when RPO thresholds are exceeded.

---

## Voting & Admin UX — Forward Outlook

### Product coherence
- Keep blocked-channel guidance consistent across proposals, proposal detail, and Telegram responses.
- Show admins an "effective vote policy" summary with current mode and implications.

### Observability and governance
- Emit reason-coded events for blocked vote attempts (`web_only` / `telegram_only`).
- Track vote accept/reject outcomes by source and reason code.
- Add audit events for backup downloads (actor, artifact, timestamp).

### Telegram identity lifecycle
- Add explicit metadata (`last_linked_at`, linked `telegram_user_id`) visible to admins.
  Delivered (2026-08-27) at the API/MCP diagnostics layer (`GET /api/members/telegram`,
  `list_member_telegram_links`); still not surfaced in the admin panel UI itself.
- Add optional self-service unlink for members with explicit confirmation UX.

### UX quality gates
- `telegram_only`: web controls hidden/disabled with clear next-step text.
- `web_only`: Telegram responses provide actionable guidance.
- Add a compact behavior matrix test suite across proposals, proposal detail, polls, and Telegram webhook flows.

---

## UX / UI Design Track (Forward)

### A) UX foundations
- Define personas (casual member, power member, admin/operator).
- Map critical journeys (first vote, Telegram linking, mode-specific voting, admin maintenance).
- Prioritize UX debt by severity.

### B) Information architecture
- Normalize nav labeling/order and Admin vs Settings boundaries.
- Add a consistent context header pattern (title, one-line purpose, primary action, help link).

### C) Design system consistency
- Introduce semantic tokens (color, spacing, typography).
- Standardize button hierarchy and reusable components (alerts, empty states, badges, tables, confirmation modals).

### D) Form UX + microcopy
- Apply clear labels, helper text, inline validation, and disabled-state rationale.
- Use concise action-oriented microcopy with explicit next steps.

### E) Accessibility + responsive gates
- Enforce keyboard navigation, focus visibility, contrast, semantic landmarks, and ARIA coverage.
- Validate mobile layouts for nav, tables, and high-risk action rows.
