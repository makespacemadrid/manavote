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

5. **Observability completion for Telegram lifecycle (P2)**
   - Add reason-coded audit events for link/unlink operations and blocked votes by policy mode.
   - Expose `last_linked_at`/`last_unlinked_at` metadata for admin diagnostics.

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
     atomically consumed before execution. Conversation history and queue state remain
     process-local and still require the shared-state work above.

3. **End-to-end natural-language webhook contract (P0)**
   - Existing functional webhook tests exercise deterministic commands and callbacks,
     while model/Telegram lifecycle pieces are primarily unit-tested.
   - Add a Flask-level test covering linked and unlinked senders, thinking-message create
     and delete, tool call, final chunk delivery, duplicate `update_id`, and queue-full UX.
   - Add an administrator test spanning proposed mutation → `/confirm` → one MCP write,
     including role removal between proposal and confirmation.

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

8. **Conversation quality and operator controls (P2)**
   - Add explicit token budgeting and model-context truncation rather than message-count
     truncation alone; publish model/timeout/queue health in admin diagnostics.
   - Evaluate Telegram `sendChatAction(typing)` or editing the temporary status message
     for smoother UX, with localization for assistant-owned deterministic messages.
   - Add opt-in, privacy-reviewed durable history only if a concrete member workflow
     requires it; keep the default ephemeral and document retention clearly.

## WS-A — Architecture Refactor (P0)

### A1. Decompose route concerns
- Split route responsibilities into focused modules (`auth`, `proposal`, `poll`, `admin`, `api`).
- Move shared orchestration helpers into route-helper or service layers.
- Register route modules consistently through app setup.

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
