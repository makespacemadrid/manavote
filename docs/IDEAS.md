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
     still only have REST-side coverage. Pagination/type errors across list endpoints
     remain open.

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

2. **Shared state for multi-worker/restart safety (P0)**
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
     `MAX_HISTORY_MESSAGES` (12) turns per chat/user and shared across workers. Bounded
     model-request queue state (the in-process worker pool limiting concurrent model
     calls) is fundamentally process-local by design and still needs an architectural
     decision — e.g. a single dedicated assistant worker, or a database/Redis-backed
     lease — rather than a like-for-like SQLite swap.

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
- Progress (2026-08-27): the `/admin` handler (627 lines) and all 11 proposal-lifecycle
  handlers moved out of `main_routes.py` into `admin_routes.py`/`proposal_routes.py`
  proper, cutting `main_routes.py` from 2368 to 1218 lines. `/about`, `/budget`,
  `/settings`, `/telegram-settings`, `/register`, and the backup-download/overbudget
  routes were already thin blueprint aliases before this. Still directly implemented in
  `main_routes.py` rather than behind a thin alias: `telegram_webhook` (~180 lines,
  genuinely cross-cutting) and `proposals()` (~155 lines, the main listing page).

### A2. Complete service/repository boundary
- Route handlers call service entry points only.
- Repositories own query composition and persistence concerns.
- Critical domain operations gain direct service-level test coverage.

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
