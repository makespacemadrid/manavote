# CHANGELOG — Delivered Roadmap Items

Last reviewed: 2026-10-08

Shipped outcomes from the roadmap, newest first. This is not a complete release
history. [IDEAS.md](IDEAS.md) contains unfinished work; [SPRINTS.md](SPRINTS.md)
records iteration scope and progress. Detailed historical findings and decisions are
preserved in the [roadmap audit archive](archive/ROADMAP_AUDITS.md).

## 2026-10-08 — Sprint 15 queued cancellation and assistant operator health (BOT-04 slice, BOT-06, OPS-03 slice)

- `/cancel` is a deterministic control path before admission: it cancels owned queued futures and atomically clears the linked member's recorded pending action in the current conversation, without model work or a new thinking message. English/Spanish replies distinguish cancelled, starting/running, and unavailable work; no committed action is claimed undone.
- Registry terminal cleanup and member/global release remain exactly once through start/cancel races, duplicate updates, early completion, submission rejection, and Telegram cleanup failure. Workers refresh identity/role before execution; relinking cannot claim prior jobs/actions or run stale queued authority.
- Added bounded process-local terminal/reason and stage-failure counters, queue/model/MCP/delivery latency summaries, and safe configuration through session-admin-only `GET /admin/assistant-health` with no-store responses. Health has no conversation contents, credentials, provider URLs, or identity labels; restart and multi-worker limits are documented.
- Validation: 872 Python tests passed, including localhost MCP transport checks and all previous sprint regressions; documentation checks passed. Running-call interruption, distributed cancellation/fleet metrics, retention, and general REST telemetry remain deferred.

## 2026-10-08 — Sprint 14 accessible and consistent member/admin interface (UX-01/02/05/06/07)

- Password, danger, and feedback dialogs share a frontend keyboard/focus controller. The password dialog has one accessible title, associated labels, focus trapping/return, Escape/backdrop/cancel handling, and clears password inputs on dismissal. Target identity is safely serialized in data attributes; server form/auth/CSRF contracts are preserved.
- Proposal quick-vote buttons use shared semantic cyan/reject styling. Removed an obsolete inline-style selector after confirming it has no template targets; existing semantic filters and table scrolling remain.
- Translated the two outstanding Admin headings and displayed existing link/unlink timestamps in configured local time with missing-history states.
- Validation: 852 Python tests passed; frontend test and production build passed. Installed Chromium verified keyboard/dialog behavior, confirmation submission, focus return, password clearing, palette, and no page overflow in English/Spanish at 375/600/1280px. The reusable synthetic-page harness is documented in TESTING.

## 2026-10-08 — Sprint 13 proposal contracts and lifecycle safety (API-01/API-02 slices, UX-08)

- Approval and over-budget rechecks now share state validation inside a SQLite write reservation; retries/concurrent callers cannot debit an approved proposal again. State, current budget, and ledger writes roll back together on failure.
- Administrator undo serializes its restore/reset and preserves existing immediate reapproval semantics. Notifications remain after commit; supported action permissions and intentional web/API differences are documented.
- Added independent REST/MCP proposal list field/type/filter/error checks and real concurrent approval/undo, ledger rollback, and recheck regressions. Consolidated the rendered proposal/poll/Telegram vote-mode coverage matrix.
- Validation: 849 Python tests passed, including localhost MCP checks; documentation checks passed. Other endpoint contracts and lifecycle transitions remain separate backlog slices.

## 2026-10-08 — Sprint 12 assistant input and secret safeguards (BOT-02, BOT-03)

- Added validated context/input/output budgets, conservative serialized UTF-8 counting before every model round, and provider `max_tokens`. Complete historical groups are trimmed; required current/tool context fails safely when it cannot fit.
- Oversized or credential-bearing input receives English/Spanish feedback; rejections release admission and clean up status messages without consuming unrelated confirmations or repeating actions.
- Configured secrets, named sensitive fields, bearer values, and credential-bearing URLs are protected across model payloads, new durable-history writes, tool errors, confirmation displays, replies, and safe failure logs. Unknown unlabelled secrets and historical-data deletion remain outside this guarantee.
- Added boundary, multi-round, persistence, and webhook regressions. Validation: 835 Python tests passed, including localhost MCP transport tests; documentation checks passed. Configuration/counting limitations and operator reason codes are documented.

## 2026-10-08 — Sprint 11 assistant member admission (BOT-01)

- Added `TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER`: a positive integer, default `1`, counting queued and running assistant jobs for each linked member across chats in one process. Invalid values prevent startup; restart to apply changes.
- Concurrent excess requests return English/Spanish busy/retry messages with `member_capacity_exceeded`, before posting thinking messages or calling model/MCP tools. Other members can use available global capacity; update deduplication and the existing executor bound are preserved.
- Member reservations release once after completion, worker/model/delivery failure, queue rejection, submission failure, or queued cancellation. Cancellation also cleans up the queued job’s thinking message.
- Busy `/confirm` and `/cancel` leave pending mutations available for retry. Existing linked-member authorization, administrator confirmation, actor/role revalidation, and deterministic commands retain their behavior.
- Added direct concurrency/executor and Flask regressions. Full combined validation: 817 Python tests passed, frontend test passed, production build and documentation checks passed. Limits remain process-local and multiply across WSGI workers; distributed fairness and per-minute rates are deferred.

## 2026-10-08 — Sprint 10 architecture boundary closure (ARCH-01)

- Classified every `legacy.*` dependency across eight blueprints and retained intentional runtime/context/compatibility adapters.
- Route modules now delegate all SQL to repositories/database initialization and domain use cases/read models to services: proposals, auth/OIDC, admin, polls, group purchases, Koins/QR, and API queries. Telegram lookups use repositories; bootstrap policy and migration checks live in `app/db/initialization.py`.
- Preserved endpoints, permissions, flashes, REST/MCP fields, filters, thresholds, money semantics, notification sequences, and runtime patch points. Failed lifecycle writes roll back before reprocessing; services borrow connections and HTTP adapters close them.
- Added direct and HTTP regressions plus SQL/web-context ownership guards. Replaced simulated/source-based lifecycle checks with real behavior tests and corrected test database isolation.
- Validation: 777 Python tests passed, frontend test passed, production build succeeded. [Ownership inventory](SPRINT_10_INVENTORY.md); [completed Sprint 10](SPRINTS.md#sprint-10-completed-2026-10-08--architecture-boundary-closure).

## 2026-10-07 — Koins MCP and shared history

- Admin MCP consumption/replenishment tools can target another member. Telegram
  requires confirmation; target attribution, input validation, and retry idempotency
  are covered. Each unit changes stock and balance together ([PR #116](https://github.com/makespacemadrid/manavote/pull/116)).
- The Koins page shows the latest 30 movements from all members, newest first, while
  personal balances remain individual ([PR #117](https://github.com/makespacemadrid/manavote/pull/117)).

## 2026-10-04 — Architecture review

- Route decomposition was confirmed complete: page handlers live in focused
  blueprints. Remaining ownership and compatibility work is Sprint 10's ARCH-01 scope.
  [Historical extraction notes](archive/ROADMAP_AUDITS.md#a1-decompose-route-concerns).

## 2026-08-29 — Telegram proposal resources

- MCP proposal lookup exposes public proposal/image URLs and exact proposal-ID
  filtering; Telegram shares images as photos. HTTPS Base URL validation, localized
  missing-URL diagnostics, and end-to-end tests protect the sharing workflow.
  [Sprint 9 delivery](SPRINTS.md#sprint-9-completed-2026-08-29--telegram-proposal-resource-sharing).

## 2026-08-27 — Roadmap and audit fixes

### Architecture and API contracts

- Extracted voting-mode policy, poll helpers, Telegram commands, shared pagination,
  voting-setting writes, proposal/poll persistence, and creation validation into
  services/repositories while retaining compatibility adapters.
- Added REST/MCP creation, pagination, statistics, and Telegram-link parity coverage;
  corrected boolean-validation, creator-error, and polls-pagination drift.
- Statistics expose page `count` and matching `total`, retain lifetime semantics,
  document field/nullability contracts, and omit email unless an admin opts in.
- REST errors use a shared stable code/message envelope; MCP retains JSON-RPC errors.
  [MCP extraction decisions](archive/ROADMAP_AUDITS.md#mcp-extraction-boundary) and
  [contract evidence](archive/ROADMAP_AUDITS.md#error-contract-matrix-expansion).

### Telegram state and confirmation

- Webhook deduplication, pending confirmations, and bounded conversation history
  persist in SQLite and are shared across workers; confirmations are consumed atomically.
- Confirmation checks actor linkage, admin role, tool-schema fingerprint, and execution
  argument digest. Mutation lifecycle events include stable reason codes.
- JSON-RPC and Telegram use the public tool registry and shared actor-authorized
  application boundary. Unclassified tools and password-bearing member creation remain
  excluded from Telegram; confirmation displays redact credentials.
- End-to-end webhook tests cover access, retries, delivery, queue-full responses,
  confirmed writes, and role removal.
  [State/worker decision](archive/ROADMAP_AUDITS.md#shared-state-for-multi-worker-safety),
  [confirmation evidence](archive/ROADMAP_AUDITS.md#confirmation-integrity-and-auditability),
  and [public boundary](archive/ROADMAP_AUDITS.md#public-mcp-application-boundary).

### Telegram routing and job diagnostics

- Forum-topic replies stay threaded, exact addressing is classified with reason codes,
  and group `/confirm@botname` / `/cancel@botname` syntax is normalized.
- Startup warns about missing bot usernames in group configurations.
- Job logs include update/chat/actor/tool context, queue wait, model latency, delivery
  outcomes, and worker failures; the executor shuts down gracefully.
  [Routing audit](archive/ROADMAP_AUDITS.md#telegram-forum-topic-routing-audit-2026-08-26).

### Identity and vote policy

- Linked/unlinked timestamps and Telegram diagnostics are available through REST/MCP;
  admins see Telegram IDs, and members can unlink with confirmation.
- Admins see the effective vote policy. Accepted/rejected votes and policy blocks emit
  reason-coded events; backup downloads include actor/artifact/time audit events.
- SSO email attachment was confirmed intentional; IdP group claims determine admin
  status on every login.
  [Identity decision](archive/ROADMAP_AUDITS.md#docs-audit-findings-requiring-a-product-decision-2026-08-26)
  and [lifecycle evidence](archive/ROADMAP_AUDITS.md#telegram-lifecycle-observability).

### UX, budget, and feedback

- Shared translated danger-action dialogs provide keyboard/focus handling; undo and
  vote withdrawal use POST. Proposal/poll actions and filters have clearer hierarchy,
  active states, title fallbacks, and distinct result colors. Pinch-to-zoom is enabled.
- Budget charts use self-hosted Chart.js, date-range controls, an explicit balance,
  separate chart/table controls, and shared currency formatting.
- Categorized feedback works through web, REST, and member-scoped Telegram MCP;
  shared validation/audit events support an Admin triage tab. Feedback skips confirmation.
- Admin navigation uses persistent tabs. Remaining modal, palette, i18n, and search
  gaps stay in IDEAS.
  [UX audit](archive/ROADMAP_AUDITS.md#delivered-uxui-audit-items) and
  [feedback scope/decisions](archive/ROADMAP_AUDITS.md#archived-member-feedback-scope).

### Reliability and regression fixes

- A single startup orchestrator validates configuration, initializes the database and
  integrations, and emits ready/degraded summaries. Typed exception boundaries replaced
  broad route catches; backup creation/failure paths emit structured lifecycle events.
- Fixed proposal status badges, the “All” filter, shared-database test assumptions,
  and subprocess interpreter selection. The regression suite no longer needs exclusions.
  [Startup notes](archive/ROADMAP_AUDITS.md#ws-b--startup-reliability-p0),
  [exception audit](archive/ROADMAP_AUDITS.md#route-exception-granularity), and
  [regression diagnosis](archive/ROADMAP_AUDITS.md#fixed-the-4-tests-repeatedly-labeled-pre-existingenvironmental-all-session).
