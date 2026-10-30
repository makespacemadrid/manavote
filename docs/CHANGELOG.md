# CHANGELOG — Delivered Roadmap Items

Last reviewed: 2026-10-29

Shipped outcomes from the roadmap, newest first. This is not a complete release
history. [IDEAS.md](IDEAS.md) contains unfinished work; [SPRINTS.md](SPRINTS.md)
records iteration scope and progress. Detailed historical findings and decisions are
preserved in the [roadmap audit archive](archive/ROADMAP_AUDITS.md).

## Unreleased — Copy retry protection, web copies and Telegram preferences

- MCP copies persist creator-scoped request keys: retries reuse the original result,
  changed arguments conflict, and fresh keys allow intentional additional copies.
  Requests without explicit keys reuse identical prior requests by default.
- Added admin-only Copy as new buttons on proposals, polls and group purchases, with
  session attribution, CSRF protection and per-form keys using the same copy service.
- Linked members can opt into private Telegram feedback-resolution notices in Settings.
  In-app notices remain guaranteed; claimed delivery attempts avoid duplicate messages,
  and missing links or delivery failures do not undo feedback resolution.
- Reworked About into one column with full-width introductory paragraphs, numbered
  proposal steps, and vertically stacked funding, tracking and Extras sections.
- Validation: full Python run passed 986 tests; follow-up Settings coverage passed.
  Five frontend tests, production build, and six bilingual Chromium layout/interaction
  checks passed.

## Unreleased — About readability

- Budget and Proposals links now wrap the original sentence words in both languages,
  retaining the existing copy rather than adding standalone links. API is also linked
  inline, and Feedback opens the same dialog through an inline text action.
- Added readable spacing, responsive funding/tracking columns, feature cards, and a
  quieter integration footer, with keyboard focus and escaped localized inline links.
- Combined validation: 973 Python tests and 5 frontend tests passed; production assets
  rebuilt. Chromium verified About inline links/feedback, hydration and Admin interactions
  in English/Spanish at 375/600/1280px.

## Unreleased — Browser build provenance

- Fingerprint frontend asset URLs to avoid reusing stale JavaScript/styles across
  deployments, and include the loaded frontend build in new browser error reports.
- Added validation and asset-change regression checks. The uploaded hydration warnings
  predate the currently deployed fixed bundle; injected wallet errors are external to
  application code and remain visible rather than being suppressed.

## Unreleased — MCP copy tools

- Added copy_proposal, copy_poll, and copy_group_purchase with optional new titles/
  questions and deadlines. Copies get new IDs/creators and fresh lifecycle/participation
  state, retaining reusable content, component prices, fees and closing settings.
- Old deadlines are cleared by default, images are independently duplicated, and
  transaction failures roll back rows and new files. Source items and budgets are unchanged.
- Telegram copies require administrator confirmation and bind the creator to the linked
  administrator. Copy operations do not send announcements; missing images yield a warning.

## Unreleased — Optional €125 group-purchase cap

- Added a creator/admin option to cap selected goods plus shared costs at €125.
  Overshooting selections are rejected without saving, and reaching €125 closes joining.
  Price/fee edits cannot bypass the cap; concurrent selection changes are serialized.
- Shows a running order total and cap status. Both new/edit forms place deadline,
  member limit and the €125 option below Add shared cost, retaining values on errors.
- Uses decimal cents and preserves the existing optional member-count closing limit.
- Validation: 937 Python tests passed, including cap boundaries, rollback, concurrent
  selections, edits, and compatibility with uncapped/member-limited orders.

## Unreleased — Error archives, feedback workflow, purchasing and Admin usability

- Error downloads now use CSRF-protected POST and atomically archive only exported
  pending records. Processed records remain viewable but are excluded from later exports;
  simultaneous downloads cannot duplicate a batch. Retains 200 pending and 200 archived.
- Group purchases support an optional distinct-member joining limit. Reaching it closes
  joining atomically without claiming an order was placed; creator ordering remains explicit.
- Feedback adds rejection, administrator item and note editing/deletion, and persistent
  in-app resolution notifications for the submitter. Admin notes remain private.
- Admin tabs use URL fragments/query parameters and survive refresh and Back/Forward.
  Fixed the React navigation text-node mismatch reported in the uploaded diagnostics.
- Coke/Coke Zero labels have large red/black titles and central branded wordmarks with
  high QR error correction; both decode to their unchanged scan URLs.
- About links to Feedback, GitHub, Budget and Proposals, describes Polls/Koins/Group
  purchases, and explains web, Telegram, MCP bot and API access in both languages.
- Validation: 933 Python tests and 5 frontend tests passed; production build passed.
  Chromium verified hydration, tab refresh, keyboard/focus, and layouts in English/Spanish
  at 375/600/1280px. Both branded QR images decode at native and printed display sizes.

## Unreleased — Browser errors in administrator reports

- Signed-in browsers report `console.error`, uncaught JavaScript errors, and unhandled
  promise rejections to the Errors tab and JSON download, labelled `browser.*`. Normal
  console behavior is preserved and reporting failures do not trigger another report.
- Reports include page paths and available stacks; URL query/fragment data and console
  objects are omitted. Session/CSRF validation, server/client limits, deduplication, and
  credential scrubbing bound intake. Admin-only viewing/downloading remains unchanged.
- Validation: 922 Python tests and 5 frontend tests passed; production assets rebuilt.

## Unreleased — Downloadable administrator error reports

- Added an Errors tab before Feedback, with expandable server warnings/errors and an
  admin-only JSON download. Reports include timestamps, severity, logger/call site, and
  available traceback locations; rendered text is escaped and responses use no-store.
- The latest 200 records persist in a separate SQLite file alongside the application
  database, shared across workers. Credentials are scrubbed on capture/export; no request
  bodies/headers, frame locals, or source lines are collected. Storage failures preserve
  console logging and show an unavailable-storage diagnostic.
- Historical container logs and raw stdout/stderr are outside capture. Browser capture
  was added in the follow-up above. OPERATIONS documents sharing and retention limits.
- Validation: all 914 Python tests passed, including admin/download authorization,
  uncaught request errors, credential redaction, persistence/retention, and storage failures.

## Unreleased — Add components while editing group purchases

- Group-purchase edits can append components with names and prices while preserving
  existing component IDs, member selections, and purchase status. The form supports
  adding/removing new rows, keyboard focus, mobile layout, and existing translations.
- Invalid/non-finite prices, duplicate added names, and totals above 30 components are
  rejected without saving the edit; submitted component fields remain available to correct.
- Validation: 906 Python tests passed, including 10 new component-edit cases;
  frontend tests and production build passed.

## 2026-10-25 — Preserve proposal drafts after invalid images

- New/edit proposal forms render validation errors with entered fields intact, including
  creation deadlines and unchecked basic supplies. English/Spanish image guidance
  explains how to retry with a JPG/PNG or submit without a new image; entered markup
  remains escaped and file inputs are not repopulated.
- Invalid contents and unsupported extensions leave proposals, votes, and notifications
  unchanged. Editing retains the current image until its replacement is committed;
  failed validation, inspection, partial uploads, or edit writes remove new files.
- Added multipart regression coverage for both languages, form recovery, successful
  retries, and preservation/cleanup of existing and replacement images.
- Validation: 896 Python tests passed, including 24 new regression cases; the three
  localhost MCP checks ran separately with socket access and loopback proxy exclusion.

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

## 30 October 2026 — UX audit implementation

Delivered responsive proposal details/cards, accessible form names and registration
markup, readable palette/action states, shared spacing/type, landmarks, configurable
About thresholds and sanitized Markdown. Added URL-persistent proposal discovery,
Budget series controls/data alternative, group total previews, signed Koins ordering,
copy preview, private member feedback history/public explanations, refreshed error
archives, Telegram linking aids and grouped Settings. See [SPEC](SPEC.md#shared-interface-and-discovery).

The [audit](UX_AUDIT_2026-10-29.md) remains the historical assessment. Physical-device,
screen-reader, live SSO/Telegram and member task research remain follow-up validation;
no broad navigation restructuring was attempted without that evidence.

Budget follow-up: removed the duplicate clickable canvas legend so labelled series
checkboxes remain the single visibility control and cannot drift from chart state.
Activity filters now initialize independently of the chart library, so a failed chart
asset does not disable ledger filtering. A frontend regression covers this failure path.
