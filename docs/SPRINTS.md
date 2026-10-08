# SPRINTS — Implementation Planning and Progress Tracking

Last updated: 2026-10-08

This document tracks implementation sequencing, active sprint scope, and completion status.
Backlog strategy and long-range direction live in [`IDEAS.md`](IDEAS.md).

## How to use this document

- Read sprints newest first; planned and active scope precede completed history.
- Completed roadmap outcomes link to [CHANGELOG.md](CHANGELOG.md); detailed historical
  audit findings and decisions link to the [archive](archive/ROADMAP_AUDITS.md).
- Keep content execution-oriented (scope, status, sequencing, blockers, and exit criteria).
- Log concrete shipped increments in the sprint progress section.
- When priorities shift, update sprint goal, checklist, and exit criteria together.

---

## Sprint sequence: Sprints 16–20

Sprints 12–15 are complete. Execute the next block in ascending order, closing each
sprint before starting the next. Detailed plans appear newest first below. This is a
dependency sequence, not a calendar or effort estimate; unresolved decisions block
their dependent implementation, not the independent discovery work.

| Order | Sprint | Backlog scope | Prerequisite / exit outcome |
|---|---|---|---|
| 1 | 16 — Proposal Mutation Safety and Contracts | API-01, API-02 | Extend Sprint 13 transaction guarantees to purchase, deletion, withdrawal, and edit; freeze the existing REST/MCP creation contract |
| 2 | 17 — Bootstrap Credentials and Key Rotation | OPS-01, OPS-02 | Define secure bootstrap retrieval and rotation rollout; preserve existing authentication while supporting overlap and retirement |
| 3 | 18 — Assistant History Retention and Localized Status | BOT-05, BOT-07 | Agree history policy and reuse Sprint 15 ownership; bounded deletion/expiry and reliable English/Spanish interaction |
| 4 | 19 — Verified Backups and Measured Query Performance | OPS-04, DATA-01; backup slice of OPS-03 | Agree recovery targets and representative fixtures; verifiable snapshots, safe health signals, and evidence-based query decisions |
| 5 | 20 — Proposal Discovery and Budget Chart Controls | UX-03, UX-04 | Validate member tasks and use Sprint 19 query evidence; accessible search/filter/sort and discoverable chart controls |

### Execution and close-out rules

- Each plan owns a bounded slice of its IDEAS IDs. Keep unfinished portions in
  [IDEAS.md](IDEAS.md); scheduling and discovery are not delivery.
- Resolve each sprint's listed decisions before dependent changes. Record intentional
  behavior changes in SPEC and preserve documented web, REST, and MCP differences.
- Reuse the existing service/repository owners, credential scrubber, job accounting,
  shared UI components, and translations. Follow [STYLE.md](STYLE.md).
- Close each sprint with its acceptance checks, canonical interface/behavior docs,
  relevant runbooks, a CHANGELOG entry, and updated progress/backlog status. Run the
  full Python suite for backend changes, frontend tests/build for changed assets, and
  documentation integrity checks throughout. Verify UI changes with keyboard use,
  English/Spanish, and the established mobile/tablet/desktop browser checks.
- Use synthetic data for performance, retention, and recovery checks. Planning does
  not authorize rotating deployed credentials, deleting live history, or restoring
  over a live database.
- Running-call cancellation (BOT-04), general REST telemetry (remaining OPS-03),
  participation analytics (DATA-02), and broader navigation redesign remain
  unscheduled. Promote them only with client capability, operator need, or feedback.

---

## Sprint 20 (Planned) — Proposal Discovery and Budget Chart Controls

### Goal and rationale

Make proposals easier to find and budget series easier to understand. The proposal
page currently mixes status and size chips without search/sort; the budget chart has
six datasets controlled through its legend. Existing chart ranges and activity-table
filters remain delivered foundations.

### Sequencing and decisions

- Starts after Sprint 19. Validate the concrete tasks of finding an older proposal
  and isolating a budget series with available member feedback; record assumptions
  and obtain task feedback during the sprint if prior evidence is unavailable.
- Decide searchable fields, allowed sort orders, status/size combinations, and default
  chart visibility before implementation. Preserve existing filter URLs or document
  compatible mappings; use query evidence to choose any needed indexes.

### Scope

1. Separate status and amount filtering, add bounded server-side proposal search and
   allowlisted sorting, and preserve selected values across navigation and pagination.
2. Add labelled, keyboard-operable chart series controls with a visible reset/default
   action. Keep date ranges and activity-table filters distinct and understandable.
3. Reuse shared styles and English/Spanish translations; cover empty results, long
   titles, selected-state announcements, and mobile control layouts.

### Acceptance checks

- Combined search/filter/sort yields deterministic results, matching counts and
  pagination where exposed; clearing controls restores the documented default.
- Query inputs are parameterized and sort expressions allowlisted; invalid inputs
  follow documented fallback/error behavior without changing proposal permissions.
- Chart controls accurately reflect visible series and compose with date ranges;
  displayed totals and underlying budget data remain unchanged.
- The selected tasks work with keyboard navigation in both languages at mobile,
  tablet, and desktop sizes; feedback confirms the controls address the recorded task.

### Deferred scope

New participation analytics/date windows (DATA-02), navigation/Admin redesign,
client-side replacement of server filtering, and unrelated chart types.

### Progress

- [ ] Record task evidence and approve interaction/query defaults.
- [ ] Implement proposal discovery controls and query regression coverage.
- [ ] Implement chart controls and bilingual responsive/keyboard checks.
- [ ] Update SPEC, relevant interface docs, TESTING, IDEAS, and CHANGELOG; pass close-out checks.

**Status:** Planned. Task evidence and control semantics must be resolved before implementation.

---

## Sprint 19 (Planned) — Verified Backups and Measured Query Performance

### Goal and rationale

Show that a recent backup can be read and measure query costs before optimizing them.
Database backups currently copy the SQLite file directly; verification must cover
concurrent writes and WAL mode rather than treating file existence as recoverability.

### Sequencing and decisions

- Starts after Sprint 18. Agree database/upload recovery-point targets, verification
  frequency and cost limits, and the session-admin operator surface before adding health.
- Define representative synthetic member/proposal/vote counts and query cases for
  correlated statistics and proposal-age filters. Record an explicit baseline and
  improvement threshold before deciding on an index or rewrite.

### Scope

1. Use a consistent SQLite snapshot mechanism, verify database readability/integrity
   and upload archive readability, and report recency separately for each backup type.
   Publish only complete snapshots and preserve current retention/manual/scheduled flows.
2. Add bounded, admin-only backup verification summaries and safe reason-coded events
   for missing, stale, unreadable, and healthy backups. Extend OPERATIONS with an
   isolated restore drill and interpretation of timestamps and recovery limits.
3. Capture reproducible query plans/timings; make only justified index/query changes.
   Record a no-change finding when the baseline does not warrant optimization.

### Acceptance checks

- A fixture backup taken during writes, including WAL mode, restores to an isolated
  location with expected committed data. Verification never writes to the live database.
- Missing/stale/corrupt/unreadable fixtures produce distinct, safe health outcomes;
  healthy database and upload fixtures pass. Failed creation leaves no published partial
  backup and does not prune the last valid snapshot.
- Operator access and output exclude credentials, conversation contents, raw exception
  bodies, and private filesystem paths; verification stays within its chosen limits.
- Recorded query cases preserve response fields, ordering, pagination/counts, age
  boundaries, and lifetime statistics. Any optimization meets the recorded threshold;
  evidence is retained whether or not code changes are warranted.

### Deferred scope

Off-site backup infrastructure, automated production restores, fleet-wide dashboards,
general REST telemetry, new analytics semantics, and unmeasured database rewrites.

### Progress

- [ ] Agree recovery targets/operator access and record query measurement fixtures.
- [ ] Implement consistent snapshots, verification, and isolated restore coverage.
- [ ] Add safe backup health/events and record query evidence; optimize only if justified.
- [ ] Update OPERATIONS, TESTING, relevant API docs, IDEAS, and CHANGELOG; pass close-out checks.

**Status:** Planned. Recovery targets, verification limits, and query baselines are decision gates.

---

## Sprint 18 (Planned) — Assistant History Retention and Localized Status

### Goal and rationale

Give durable SQLite conversation history a documented lifetime and deletion path,
and finish the selected deterministic English/Spanish interaction audit. Message-count
bounds already exist, but they do not define retention; thinking and some confirmation
or failure messages still require localization.

### Sequencing and decisions

- Starts after Sprint 17. Agree retention duration, expiry scheduling, member deletion
  controls, and operator access. Define whether deletion covers only active storage or
  backup expiry as well, and document any delayed removal from retained backups.
- Specify history-only deletion separately from `/reset`, which also clears pending
  confirmations. Use the existing member/chat/sender ownership and decide how deletion
  interacts with in-flight jobs so an old job cannot recreate deleted history.

### Scope

1. Implement the agreed history expiry/deletion rules with bounded cleanup, documented
   timestamp semantics, and safe behavior for existing rows and process restarts.
2. Audit deterministic status, confirmation, cancellation, reset, and error messages;
   localize the selected gaps without relying on the model to translate control text.
3. Improve temporary status feedback using the existing Telegram client capabilities.
   Preserve chunked final replies and cleanup even when status edits/deletions fail.

### Acceptance checks

- Persisted and fallback history honor expiry/deletion, including boundary timestamps,
  repeated requests, restarts, shared chats, and changed member links.
- Deleting one conversation cannot affect another actor; in-flight append/delete races
  follow the agreed policy. Pending confirmations and webhook deduplication records
  retain their independent ownership, expiry, and replay guarantees.
- Deterministic messages work in both languages for normal, confirm/cancel, busy,
  timeout, and delivery-failure paths; long answers are delivered in ordered chunks.
- Missing temporary messages and transport failures do not leak history, duplicate a
  committed tool action, or release job capacity before execution ends.

### Deferred scope

Running HTTP-call interruption and distributed cancellation (BOT-04), model-output
translation, a conversation export interface, and unrelated pending-action retention changes.

### Progress

- [ ] Document retention/deletion/access rules and in-flight history policy.
- [ ] Implement history lifecycle with ownership and persistence/race coverage.
- [ ] Localize selected interaction gaps and verify status/chunk delivery failures.
- [ ] Update SPEC, Telegram reference, OPERATIONS, TESTING, IDEAS, and CHANGELOG; pass close-out checks.

**Status:** Planned. Retention and deletion semantics must be settled before data-lifecycle changes.

---

## Sprint 17 (Planned) — Bootstrap Credentials and Key Rotation

### Goal and rationale

Remove the static development bootstrap-password fallback and let operators replace
REST/MCP keys with an overlap period. Existing accounts, explicit bootstrap passwords,
and production refusal without an initial secret are compatibility requirements.

### Sequencing and decisions

- Starts after Sprint 16. Select a secure operator retrieval mechanism for a generated
  development-only bootstrap secret; define one-time retrieval and restart/failure behavior.
- Define active/next key configuration independently for REST and MCP, overlap and
  retirement semantics, restart requirements, and rollback steps. Preserve existing
  key locations, transport envelopes, and disabled/unconfigured behavior.

### Scope

1. Generate a strong development bootstrap secret only when an administrator is
   actually being created; make it securely retrievable without logging its contents.
2. Share constant-time key acceptance logic while preserving REST and MCP authorization
   boundaries, including HTTP/TCP and internal assistant calls where applicable.
3. Extend credential scrubbing to every new configuration/retrieval surface and
   document a staged rotation procedure: configure overlap, migrate callers, retire old key.

### Acceptance checks

- Fresh development bootstrap, explicit configured password, production refusal,
  deterministic test fixtures, and existing-account restarts are covered. Concurrent
  bootstrap attempts cannot replace an existing administrator or expose extra secrets.
- Active-only, overlap, new-only retirement, missing/invalid credentials, and independent
  REST/MCP key pairs preserve each transport's success and rejection contracts.
- Assistant readiness and internal MCP authentication remain correct during overlap
  and after retirement; configured next keys are scrubbed from model/history/log outputs.
- Retrieval/rotation failure tests and documentation show usable recovery without
  exposing passwords or keys in responses, routine logs, or repository files.

### Deferred scope

Executing production credential rotation, per-user/scoped tokens, OAuth replacement,
and unrelated Telegram/OIDC secret rotation.

### Progress

- [ ] Define bootstrap retrieval and rotation/retirement configuration.
- [ ] Implement development bootstrap safeguards and migration coverage.
- [ ] Implement overlap acceptance, assistant compatibility, and secret-scrubbing checks.
- [ ] Update QUICKSTART/sample configuration, APIDOC, OPERATIONS, IDEAS, and CHANGELOG; pass close-out checks.

**Status:** Planned. Secure retrieval and rotation rollout semantics are decision gates.

---

## Sprint 16 (Planned) — Proposal Mutation Safety and Contracts

### Goal and rationale

Extend approval/undo safety to the remaining mutable proposal operations. Purchase,
deletion, withdrawal, and edit currently check proposal state before acquiring a
write transaction, allowing state to change between validation and the mutation.

### Sequencing and decisions

- Builds on completed Sprints 10 and 13. Inventory current permissions, missing-row
  behavior, retry behavior, and side effects for these operations before changing guards.
- Select REST proposal creation and the existing MCP `create_proposal` tool as the
  contract pair. Freeze accepted fields, defaults, response types, and error mapping in
  their canonical references; preserve intentional web/API creator-vote and basic-supplies
  differences. MCP has no proposal-edit tool; this sprint does not add one.

### Scope

1. Keep state/permission checks and dependent writes inside the existing service-owned
   write transaction for purchase, deletion, withdrawal, and web/API edit. Reuse guards
   only where policies match; run reprocessing/notifications after the transaction closes.
2. Protect the selected REST/MCP creation contract with inbound validation and outbound
   compatibility coverage while preserving distinct transport/authentication behavior.
3. Add deterministic interleaving and rollback checks for mutation versus approval/undo,
   including deletion of related votes/comments and edit of eligibility fields.

### Acceptance checks

- A mutation cannot act on stale eligibility after another connection processes the
  proposal; rejected operations leave proposal, votes, comments, budget, and ledger intact.
- Purchase remains available to any signed-in member only while approved; active-only
  edits/deletion/withdrawal preserve documented ownership/admin rules and missing-row behavior.
- Concurrent approval cannot consume an outdated amount or lose committed votes;
  retries preserve documented outcomes and failures roll back all dependent writes.
- The selected REST/MCP creation pair covers valid requests, invalid fields/types,
  creator validation, credentials, and stable success/error envelopes. REST edit preserves
  missing/processed-proposal errors and partial-update defaults. Delivered proposal-list
  contracts and assistant confirmation requirements remain covered.

### Deferred scope

Aligning intentional web/API policies, new MCP mutation tools or proposal statuses,
broad schema frameworks, and unrelated endpoint conversion. Approval/undo and
proposal-read protections remain delivered.

### Progress

- [ ] Record mutation policies/interleavings and the selected contract baseline.
- [ ] Move dependent validation/writes into transactions with rollback/race coverage.
- [ ] Add REST/MCP creation and REST edit compatibility checks; update canonical references.
- [ ] Update SPEC, TESTING, IDEAS, and CHANGELOG; pass close-out checks.

**Status:** Planned. First sprint in the next execution block; no implementation started.

---

## Completed sequence: Sprints 12–15

Sprint status is recorded in each section and updated as work completes. This is a
dependency sequence, not a calendar or effort estimate. Detailed plans remain newest first;
execute them in ascending order after Sprints 10–11.

| Order | Sprint | Backlog scope | Prerequisite / exit outcome |
|---|---|---|---|
| 1 | 12 — Assistant Input and Secret Safeguards | BOT-02, BOT-03 | Build on Sprint 11 admission; bounded model requests and tested credential boundaries |
| 2 | 13 — Proposal Contracts and Lifecycle Safety | API-01, API-02, UX-08 | Use Sprint 10 service owners; stable proposal-read contracts and safe approval/undo processing |
| 3 | 14 — Accessible and Consistent Member/Admin UI | UX-01, UX-02, UX-05, UX-06, UX-07 | Reuse shared dialogs and Sprint 13 policy expectations; keyboard, responsive, and bilingual fixes |
| 4 | 15 — Queued Assistant Cancellation and Operator Health | BOT-04, BOT-06, assistant slice of OPS-03 | Build on Sprint 11 admission and Sprint 12 safe boundaries; owned cancellation and actionable aggregate health |

### Historical execution and close-out rules

- Use [IDEAS.md](IDEAS.md) for the remaining scope behind each ID. A bounded slice
  closes only its stated acceptance checks; retain unfinished portions in the backlog.
- Resolve the listed model, policy, and operator decisions before dependent changes.
  Preserve current behavior until an intentional change is documented in SPEC.
- Keep SQL in repositories and policy in services; these plans extend the Sprint 10
  boundaries rather than reopening the route decomposition.
- Each sprint finishes with relevant regression checks, canonical behavior/interface
  documentation, and a CHANGELOG entry for delivered outcomes. Run the full Python
  suite for backend changes; run frontend tests/build when UI assets change. Include
  documentation integrity checks in every close-out.
- This block deferred retention/deletion, broader assistant interaction, bootstrap/key
  rotation, backup verification, query measurement, analytics, and search/chart work.
  Selected slices now have plans in Sprints 16–20; their decision gates still apply.

---

## Sprint 15 (Completed 2026-10-08) — Queued Assistant Cancellation and Operator Health

### Goal and rationale

Give linked members a reliable way to cancel their queued assistant work and give
operators a safe explanation of saturation and failures. Sprint 11 already handles
cancelled-future cleanup; this sprint adds user ownership and aggregate visibility,
not another executor or admission implementation.

### Sequencing and decisions

- Requires Sprint 11 admission/release behavior and Sprint 12 credential boundaries.
- `/cancel` attempts both owned queued-job and pending-action cancellation, reporting
  each outcome without a new admission slot. Preserve linked actor checks.
- Job ownership is member plus chat/Telegram sender, matching history, including group chats and relinking.
  State that the registry and counters are process-local. Define truthful behavior
  when another WSGI worker owns the job; do not claim cross-worker cancellation.
- The selected surface is session-admin-only `GET /admin/assistant-health`, with no-store
  responses, restart-reset process-local counters, and capacity-based saturation status.

### Scope

1. Register and remove queued/running futures with safe actor/conversation ownership.
   Route `/cancel` through a deterministic control path before model admission so a
   member with a full slot can cancel their own queued work without calling the model.
2. Use `Future.cancel()` only for queued work. Distinguish successful cancellation,
   already-running work, no owned job, and cleared pending mutations in English and
   Spanish. Retain cleanup and exactly-once admission release; remove terminal entries.
3. Add assistant-only counters for queued/active/rejected/completed/failed/cancelled
   jobs and latency summaries for queue wait, model, MCP, and delivery. Reuse existing
   events and reason codes; avoid actor/chat labels in aggregate metrics.
4. Expose safe model identifier, timeout, configured capacities, and health summaries
   through the chosen operator path. Document saturation, provider/tool failures,
   delivery failures, process restarts, and multi-worker interpretation in OPERATIONS.

### Acceptance checks

- Cancelled queued work never calls the model or MCP and never sends a final answer;
  its thinking message is cleaned up and both member/global capacity are reusable.
- Start/cancel and complete/cancel races, repeated cancellation, callback failure,
  duplicate updates, and terminal registry cleanup preserve exactly-once accounting.
- A member cannot cancel another member's job, including in a shared chat; unlinked
  callers and changed identities cannot gain control of prior jobs.
- Running work returns an accurate status without claiming interruption or rollback.
  Pending-mutation cancellation and `/confirm` authorization remain covered.
- Controlled failure fixtures distinguish admission, model, MCP, and delivery failures;
  terminal counts do not double count, and active/queued gauges return to zero.
- Operator output contains no prompts, tool arguments/results, secrets, or
  credential-bearing URLs; authorization and process-local limitations are tested.

### Deferred scope

Running HTTP-call interruption, stale-result suppression for running mutations,
distributed queues/cancellation, fleet-wide metrics, durable-history deletion, and
general REST request telemetry. OPS-03 remains open beyond the assistant slice.

### Progress

- [x] Define cancellation ownership, pending-action interaction, and operator access.
- [x] Implement queued-job control and localized outcomes with race coverage.
- [x] Add aggregate health and stage latency with safe output checks.
- [x] Update SPEC, Telegram reference, OPERATIONS, TESTING, and CHANGELOG; pass close-out checks.

**Status:** Complete. 872 Python tests passed; cancellation races, ownership, stage telemetry, operator access, and documentation checks passed.

---

## Sprint 14 (Completed 2026-10-08) — Accessible and Consistent Member/Admin UI

### Goal and rationale

Close the verified password-dialog accessibility gap and small interface inconsistencies
without a page redesign. The Admin modal still has duplicated headings and manual inline
open/close handling; responsive CSS still selects literal inline-style text, and two
Admin section headings bypass translation.

### Sequencing and prerequisites

- Follow Sprint 13 policy characterization so UI actions continue to match server rules.
- Reuse the shared dialog behavior and progressive hydration rules in
  [STYLE.md](STYLE.md). The selector audit found no remaining template targets; remove that obsolete rule and retain semantic filter/table styling.
- Verify the existing link diagnostic fields and timestamp semantics; display them
  without creating a new identity API or exposing them outside administrator views.

### Scope

1. **UX-01:** Give `changePasswordModal` one labelled title, associated input labels,
   modal semantics, initial focus, focus trapping/return, and Escape handling. Reuse
   shared dialog behavior and move touched inline interaction code to frontend modules.
2. **UX-02 / UX-05:** Remove quick-vote palette overrides and replace the fragile
   responsive selector with semantic classes on its actual targets. Keep the same
   server-rendered actions, vote modes, layouts, and selected state.
3. **UX-06:** Translate `Full Proposal History` and `Backup Uploaded Images` in English
   and Spanish, along with new accessible labels and timestamp copy.
4. **UX-07:** Show the existing `last_linked_at` / `last_unlinked_at` diagnostics in the
   Admin member view with explicit local-time formatting and missing-value states.

### Acceptance checks

- Keyboard users can open, navigate, submit, and dismiss the password dialog; focus
  returns to its trigger. There is one accessible title and each input has a label.
- CSRF, administrator authorization, target member, password validation, and submitted
  field names remain unchanged. Password values do not enter logs or browser persistence.
- Shared danger/feedback dialogs continue to work; rendered markup and hydrated UI
  retain compatible semantics and existing server-rendered page content.
- List/detail vote styles agree; supported vote modes and action visibility match
  Sprint 13's matrix. Use a focused component regression where behavior changes.
- Inspect 375px, 600px, and 1280px layouts: no page overflow or clipped primary controls;
  intentional table scrolling stays usable. No selector depends on inline-style text.
- Both languages render translated headings and labels; link timestamps respect local
  time and show useful fallbacks for never-linked or missing historical timestamps.
- Relevant Flask/UI checks and frontend tests/build pass; record manual keyboard,
  responsive, and language verification where automated coverage is insufficient.

### Deferred scope

Proposal search/sort/filter redesign (UX-03), chart-density controls (UX-04), navigation
restructuring, a full Admin rewrite, and new Telegram-link management capabilities.

### Progress

- [x] Audit shared dialog reuse, responsive selector targets, and timestamp semantics.
- [x] Implement the password-dialog accessibility fixes with form-contract checks.
- [x] Apply semantic styles, translations, and existing diagnostic timestamp display.
- [x] Complete keyboard/responsive/language verification and update CHANGELOG; pass close-out checks.

**Status:** Complete. 852 Python tests passed; frontend test/build and six real Chromium language/viewport checks passed.

---

## Sprint 13 (Completed 2026-10-08) — Proposal Contracts and Lifecycle Safety

### Goal and rationale

Protect proposal behavior after Sprint 10's ownership extraction. The services are
already in place; the next useful step is explicit contracts and transition invariants,
especially repeated approval processing and undo budget effects.

### Sequencing and decisions

- Work within `ProposalService` and `proposal_actions_service`; characterize current
  behavior before extracting shared guards or changing transactions.
- Record the lifecycle/permission matrix, including supported and unsupported actions,
  over-budget rechecks, purchase flags, deletion, withdrawal, and undo followed by reapproval.
- Keep intentional transport differences explicit. Web creation adds the creator's
  vote; web editing clears the basic-supplies flag above €20, while the current API edit
  path does not. Decide any alignment separately from contract-preserving work.

### Scope

1. **API-01:** Define compatibility checks for REST `GET /api/proposals` and MCP
   `list_proposals`: input validation, status/age filters, pagination, ordering, field
   types/nullability, vote aggregates, and original/public/image URLs where supported.
   Preserve each transport's distinct envelope, fields, and authentication.
2. **API-02:** Consolidate approval/over-budget/undo validation within existing service
   owners. Make repeated processing safe and keep proposal state, current budget, and
   budget ledger consistent on success, rejection, retry, and database failure.
3. Characterize undo's existing restore-and-reprocess behavior, including immediate
   reapproval. Test permissions and purchase/deletion/withdrawal rejection paths;
   do not expand this slice into every lifecycle operation.
4. **UX-08:** Consolidate a compact coverage matrix for supported proposal vote modes
   on list/detail pages, poll controls, and deterministic Telegram guidance. Reuse
   existing tests and add only uncovered policy cases; do not add new Telegram vote tools.
5. Put exact fields in [REST](interfaces/REST.md) and [MCP](interfaces/MCP.md) references,
   product transition rules in SPEC, and verification guidance in TESTING.

### Acceptance checks

- Existing clients keep their fields, types, ordering, filters, pagination, auth, and
  REST error/MCP JSON-RPC envelopes. Additive transport differences are documented.
- Repeated or concurrent approval processing cannot debit a proposal's budget or add
  the same approval ledger effect twice. Over-budget rechecks apply one valid transition.
- Failed database writes leave proposal state, budget balance, and ledger consistent;
  undo restores the matching amount and its subsequent processing follows the stated rule.
- Non-administrators cannot undo approval; purchase/delete/withdraw permissions and
  processed/missing-proposal outcomes retain their characterized contracts.
- Supported vote modes render matching controls and guidance across the selected
  surfaces; rejected actions remain enforced on the server.
- Contract/service/integration regressions, the full Python suite, and documentation
  checks pass. Any intentional policy change has an explicit SPEC decision.

### Deferred scope

All-endpoint schema generation, broad API validation rewrites, new lifecycle states,
purchase-permission changes, web/API policy alignment, and new analytics/search features.
API-01 and API-02 remain open for unselected contracts and transitions.

### Progress

- [x] Record current transport contracts, lifecycle invariants, and cross-channel coverage.
- [x] Add proposal-read contract checks and shared approval/undo validation.
- [x] Cover retries, concurrent processing, database failures, permissions, and uncovered vote-mode cases.
- [x] Update canonical references, SPEC, TESTING, and CHANGELOG; pass close-out checks.

**Status:** Complete. 849 Python tests passed; concurrent transition, contract, vote-mode matrix, and documentation checks passed.

---

## Sprint 12 (Completed 2026-10-08) — Assistant Input and Secret Safeguards

### Goal and rationale

Bound assistant model requests and protect credential boundaries before adding more
assistant controls. Sprint 11 caps outstanding jobs, but the agent still limits history
by message count and tool rounds; neither bounds one large prompt or tool result.

### Sequencing and decisions

- Build on completed Sprint 11 without changing admission, webhook deduplication,
  actor binding, or administrator confirmation behavior.
- Measure representative prompts, tool schemas/results, and history for the configured
  model. Choose context/input limits, an output reserve, and a tokenizer or documented
  conservative estimator compatible with that provider; avoid an arbitrary model limit.
- Define a credential threat model: configured credentials, known sensitive fields,
  provider/MCP failure payloads, and credential-bearing URLs. Document the limits of
  detecting arbitrary secrets in free text; do not promise perfect secret recognition.

### Scope

1. **BOT-02:** Add validated input/context configuration and a shared guard before every
   outbound model round. Include system instructions, current input, tool schemas,
   history, and tool results in the budget, reserving response capacity.
2. Reject oversized current input with actionable English/Spanish feedback. Trim old
   history by complete conversation/tool groups; preserve current input, actor policy,
   and required tool-call/result pairing. If the required context cannot fit, fail safely
   rather than silently truncating instructions or malformed JSON/tool results.
3. **BOT-03:** Keep `create_member` excluded and unclassified tools denied. Apply the
   chosen credential-handling rules before model requests, history writes, operational
   logging, confirmation text, MCP error presentation, and final Telegram replies.
   Preserve legitimate proposal URLs, amounts, IDs, and existing allowed tool arguments.
4. Add configured-secret and sensitive-field fixtures through success, provider/MCP
   failure, persistence, and delivery paths. Document limits and failure reason codes in
   QUICKSTART, SPEC, Telegram reference, and OPERATIONS.

### Acceptance checks

- Every model round stays within the configured request budget and response reserve;
  tests include exact boundaries, Unicode, oversized input/history/tool schemas/results,
  and multiple tool rounds. Invalid configuration fails with an actionable message.
- History trimming never leaves an orphaned tool result or drops current actor policy.
  An unfit required prompt produces safe feedback without another outbound model request.
- Selected credentials and sensitive fields never reach tested model payloads, history,
  logs, or replies, including exception bodies and credential-bearing URLs; safe diagnostic
  metadata and ordinary domain values remain usable.
- Budget or secret rejection releases admission, cleans up status messages, and neither
  retries a committed mutation nor consumes an unrelated pending confirmation.
- Existing schema filtering, actor binding, confirmations, role changes, webhook
  deduplication, and English/Spanish busy responses retain their behavior.
- Mocked-boundary regressions, the full Python suite, and documentation checks pass;
  no real credentials or provider calls are required for validation.

### Deferred scope

Enrollment/password creation through Telegram, durable-history retention or deletion,
running-call cancellation, distributed limits, per-minute quotas, and broad status redesign.

### Progress

- [x] Measure model context and define limits, counting strategy, and credential rules.
- [x] Implement per-round budgeting, safe history trimming, and localized rejection.
- [x] Cover selected credential boundaries and success/failure regressions.
- [x] Document configuration and shipped guarantees in canonical docs/CHANGELOG; pass close-out checks.

**Status:** Complete. 835 Python tests passed; mocked boundary and documentation checks passed.

---

## Latest completed sprints

## Sprint 11 (Completed 2026-10-08) — Per-member Assistant Admission

### Goal and rationale

Prevent one linked member from occupying all assistant job slots while preserving
webhook retries, existing confirmations, and the global executor bound. This is the
bounded **BOT-01** slice recorded in [CHANGELOG.md](CHANGELOG.md).
`BoundedExecutor.submit()` originally had only a process-wide semaphore.

### Sequencing and prerequisites

- Sprint 10 closed after 777 Python tests and frontend checks passed.
- Its inventory records Telegram admission/executor ownership as an intentional
  integration boundary; Sprint 11 extends that boundary without moving persistence.
- Use the existing database-backed linked member identity. Admission accounting is
  process-local, matching the existing executor; document the multiplication of limits
  under multiple WSGI workers.

### Scope

1. Add a configurable outstanding-job limit per linked member, counting queued and
   running model work across chats in one process. Start with a default of one;
   validate positive integer configuration and document tuning.
2. Acquire member admission before submitting model work. Release it on global queue
   rejection, submit failure, job success/failure, or queued cancellation. Make the
   acquire/release operations safe under concurrent webhook requests.
3. Rejected requests produce a localized, actionable busy/retry response and a stable
   `member_capacity_exceeded` reason code. Do not reveal other members' identities,
   prompts, or jobs; avoid leaving a thinking message behind.
4. Preserve webhook update deduplication, the global queue bound, authorization, and
   administrator `/confirm` semantics. Inspect command dispatch so a queued/running
   model request cannot inadvertently consume or discard a pending mutation.
5. Add direct admission/executor tests and Flask webhook regressions with mocked
   outbound model/Telegram calls. Document the variable and process-local semantics
   in QUICKSTART/OPERATIONS; record shipped behavior in SPEC and CHANGELOG.

### Acceptance checks

- Two concurrent model requests for the same linked member in different chats yield
  at most the configured outstanding count; another member can use available capacity.
- Failed submission, queue-full rejection, worker/model/delivery failure, normal
  completion, and cancellation each leave admission reusable exactly once.
- Duplicate `update_id` does not reserve a second slot or run the model again.
- Over-limit requests neither call the model/MCP nor leave orphaned thinking messages.
- Unlinked senders and member/admin authorization keep their existing behavior;
  confirmation, cancellation of pending mutations, and role-change checks still pass.
- Busy/retry messages render in English and Spanish; logs contain safe metadata only.
- The full Python suite, frontend tests, and relevant build checks pass; documented
  configuration and operational limits match the implementation.

### Deferred from this sprint

Token/context budgeting (BOT-02), broader secret handling (BOT-03), `/cancel` for
running model calls (BOT-04), retention controls (BOT-05), aggregate telemetry (BOT-06),
and distributed fairness/persistent queues. This sprint limits outstanding jobs;
rate-per-minute limits and strict queue scheduling need separate usage evidence.

### Progress

- [x] Confirm integration ownership: process-local member accounting beside the singleton bounded executor; default one outstanding job per linked member.
- [x] Implement concurrent-safe member accounting and idempotent release after completion, worker/delivery failure, queue rejection, submit failure, and queued cancellation.
- [x] Add English/Spanish rejection before thinking/model work, direct admission/executor tests, concurrent/cross-chat Flask checks, and pending-confirmation/cancellation preservation.
- [x] Document configuration, process-local worker limits, cancellation/confirmation behavior, and reason codes. Full validation: 817 Python tests passed; frontend test/build and documentation checks passed.

**Status:** Complete; default one outstanding job per linked member per process.

Delivery details and configuration are in [CHANGELOG.md](CHANGELOG.md),
[QUICKSTART.md](QUICKSTART.md), and [OPERATIONS.md](OPERATIONS.md).

---

## Sprint 10 (Completed 2026-10-08) — Architecture Boundary Closure

### Goal

Finish the route/service ownership work without treating line-count reduction as the
objective. Every remaining dependency on `main_routes` must be classified as an
intentional compatibility adapter, a request-context adapter, or misplaced domain/query
logic; only the last category moves.

### Scope

1. Inventory `legacy.*` dependencies in every route blueprint and record the intended
   owner for each shared function.
2. Move remaining query composition into repositories and domain decisions into
   services where an ownership violation still exists.
3. Keep thin wrappers when they preserve endpoint compatibility, Flask request context,
   or established patch points; document why they remain.
4. Retarget tests to the owning service or repository while retaining route-level
   coverage for authentication, redirects, flashes, and response shape.
5. Update `DIAGRAMS.md`, `SPEC.md`, and the testing map only when their represented
   boundary changes.

### Explicit non-goals

- No feature work or UI redesign.
- No compatibility-wrapper removal solely to make `main_routes.py` smaller.
- No broad repository rewrite; changes must be independently reviewable slices.
- No REST/MCP contract changes unless required to correct demonstrated drift.

### Exit criteria

- Every `legacy.*` route dependency is classified and intentional.
- Route modules contain request orchestration, not SQL or reusable domain policy.
- Moved behavior has direct unit coverage plus relevant route regression coverage.
- The full Python suite and frontend tests pass.
- The architecture and testing documents match the resulting boundaries.

### Progress

- [x] Inventory and classify all 45 unique `legacy.*` attributes across the eight route blueprints; record direct SQL/domain violations separately in [SPRINT_10_INVENTORY.md](SPRINT_10_INVENTORY.md).
- [x] Select slice 1: budget and proposal-list read models plus duplicate budget/member/vote read wrappers.
- [x] Extract slice 1 into budget/proposal-page services and repositories; retain request/runtime adapters and existing filter, vote, threshold, and money semantics.
- [x] Add direct read-service regression tests and replace a route-source inspection with behavioral approval-aggregation coverage.
- [x] Validate slice 1: 704 Python tests passed, the frontend test passed, and the frontend build succeeded. Documentation links/reachability and whitespace checks passed.
- [x] Extract slice 2: purchase/unpurchase, active-proposal deletion, and admin comment editing/deletion into `proposal_actions_service` and repositories; preserve permissions, redirects/flashes, and timestamps.
- [x] Add 33 use-case/HTTP regression cases for status/role rejection, dependent deletion, rollback, connection cleanup, and blank comment edits.
- [x] Validate slices 1–2 together: 737 Python tests passed. The frontend test/build remain valid from slice 1; slice 2 changes no frontend source. Documentation checks passed.
- [x] Extract the remaining route query/write violations: proposal lifecycle/detail/edit/create, auth/OIDC, REST reads/updates, polls, QR, group purchases, admin actions/page reads, bootstrap, and two Telegram lookup queries.
- [x] Add direct auth and closure-use-case coverage plus guards against SQL in routes and Flask/web imports in extracted services; retain HTTP regression coverage and runtime patch points.
- [x] Final validation: 777 Python tests passed, frontend test passed, production build succeeded, and documentation checks passed. All route SQL is repository/initialization-owned.

**Status:** Complete; the classified runtime/compatibility adapters remain intentional.

---

## Delivery history through 2026-10-07

Sprints 3 through 9 are complete. Sprint 7 delivered the UX/UI, budget-visualization,
and member-feedback work scoped from the dedicated UX audit. Sprint 8 then completed
the public MCP application boundary: JSON-RPC and Telegram now share a transport-neutral
execution layer with explicit actor policy. Sprint 9 completed reliable
proposal-resource discovery and sharing through Telegram natural chat, including
missing-Base-URL operator diagnostics. Forward-looking work is tracked in
[`IDEAS.md`](IDEAS.md) until the next sprint is scoped.

### Subsequent shipped increments (September–October 2026)

- Member feedback shipped across the web overlay, REST, and member-scoped Telegram MCP,
  with an Admin triage tab and structured events.
- Proposal MCP results gained voter details plus URL/image attachment support; Telegram
  sends proposal images as photos when available.
- Poll creation now announces consistently from web, REST, and MCP, and multi-select
  polls are supported across web and Telegram without destructive form resubmission.
- Telegram linking now defaults to a passwordless, signed browser-confirmation flow;
  group assistant routing recognizes exact mentions, bot replies, and configured forum
  topics.
- Koins shipped with configurable/deactivatable categories, QR debit labels, member
  balances and rankings, lifetime per-item consumption, and administrator ledger
  corrections. Admin MCP can now credit/debit another member through confirmed
  ledger actions, and recent movements show all members (PRs #116–#117).
- Navigation gained emoji labels, and the desktop layout was widened for large screens.

---

## Sprint 9 (Completed 2026-08-29) — Telegram Proposal Resource Sharing

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

## Sprint 7 (Scoped 2026-08-27) — UX/UI: Button Layout, Placement, Budget Graph & Feedback

### Why this scope
Sprints 3-6 focused entirely on backend hygiene: MCP/REST convergence, exception
handling, and structured audit logging. None of that touched what members actually
look at. A dedicated UX/UI audit ([archived UX/UI audit](archive/ROADMAP_AUDITS.md#uxui-audit-2026-08-27)) read every
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
it's scoped end-to-end (schema, service, REST, MCP, admin panel) per the [archived feedback scope](archive/ROADMAP_AUDITS.md#archived-member-feedback-scope), so the Telegram assistant
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
   scoped per the [archived feedback plan](archive/ROADMAP_AUDITS.md#archived-member-feedback-scope).
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
     implementation (leaning no — see the [archived feedback decision](archive/ROADMAP_AUDITS.md#archived-member-feedback-scope)); flag for a second
     opinion since it would be the first mutating tool to deliberately skip that
     pattern.
   - Admin panel: new "Feedback" section in `admin.html` listing submissions with
     status/category badges (reusing `.status`/`status-*` classes, not one-off inline
     colors) and a mark-reviewed/resolved action.
   - First slice explicitly excludes admin notifications, a member-facing status view,
     and attachments — see the [archived feedback non-goals](archive/ROADMAP_AUDITS.md#explicit-non-goals-for-the-first-slice).

### Explicitly deferred (with reasoning, not just left off)
- **Public MCP application boundary ([delivery record](CHANGELOG.md#telegram-state-and-confirmation), P1)** — real architectural value,
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
reach a write operation. Two smaller [historical observability items](CHANGELOG.md#telegram-routing-and-job-diagnostics)
round out the sprint since they're cheap to close now that the structured-logging pattern
(reason codes, correlation IDs) is well established everywhere else.

### Goals
1. **Confirmation integrity and auditability** — ✅ closed 2026-08-27. Closes the [confirmation audit](CHANGELOG.md#telegram-state-and-confirmation) (P1).
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
   the [Telegram lifecycle observability audit](CHANGELOG.md#identity-and-vote-policy) (P2).
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
   the [forum-routing observability audit](CHANGELOG.md#telegram-routing-and-job-diagnostics) (P2).
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
- **Public MCP application boundary ([delivery record](CHANGELOG.md#telegram-state-and-confirmation), P1)** — real architectural value
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
- **Fair-use limits and cancellation ([BOT-01](CHANGELOG.md#2026-10-08--sprint-11-assistant-member-admission-bot-01) / [BOT-04](IDEAS.md#bot-04--cancel-running-model-work-safely-p2))** — same scale-appropriate
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

## Sprint 5 (Completed 2026-08-27) — MCP/REST Convergence + Exception Hygiene

### Why this scope
Sprint 4's A2 work (moving `main_routes.py`'s embedded logic into
`app/services/`/`app/repositories/`) wasn't just cleanup — applying it directly caught two
real REST/MCP behavior drifts (`basic_supplies` coercion, `created_by` error-code
mismatch) and one real feature gap (polls pagination missing from REST). All three
existed *because* REST and MCP independently reimplemented the same query/validation
logic instead of sharing it. `app/mcp_server.py` (872 lines, 17 direct SQL call sites for
proposal listing, poll listing/creation, voting-setting reads/writes, and member
creation) is the last large block of that pattern — this is the [MCP extraction audit](CHANGELOG.md#architecture-and-api-contracts), and finishing it is the highest-leverage thing left: it doesn't just
document parity, it makes future drift structurally harder to introduce.

### Goals
1. **MCP extraction boundary** — ✅ closed (2026-08-27), see the three slices below.
   Move `app/mcp_server.py`'s embedded proposal-listing,
   poll-listing/creation, voting-setting, and member-creation logic into
   `app/services/`/`app/repositories/` modules shared with the equivalent REST routes,
   one use case at a time (same incremental, test-verified-after-each-slice approach used
   for A2). Closes the [MCP extraction audit](CHANGELOG.md#architecture-and-api-contracts) and is the natural
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
     says otherwise (see slice 1). Full details in the [extraction archive](archive/ROADMAP_AUDITS.md#mcp-extraction-boundary).
2. **Route exception granularity** — replace the 19 broad `except Exception` blocks
   across 8 files (`mcp_server.py`, `backup_service.py`, `main_helpers.py`,
   `api_routes.py`, `poll_routes.py`, `admin_routes.py`, `telegram_routes.py`,
   `auth_routes.py`) with typed exceptions and stable reason codes, so failures are
   diagnosable instead of collapsing into one generic message. Closes the [route exception audit](CHANGELOG.md#reliability-and-regression-fixes).
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
   Advances the [job diagnostics delivery](CHANGELOG.md#telegram-routing-and-job-diagnostics);
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
- **Fair-use limits/cancellation, conversation quality controls** (current [BOT-01/BOT-02/BOT-04/BOT-07 backlog](IDEAS.md#telegram-assistant)) — same reasoning as Sprint 4's model-request-queue decision: this app's
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
- **OIDC/SSO silent-attach-by-email trust model** ([archived identity decision](archive/ROADMAP_AUDITS.md#docs-audit-findings-requiring-a-product-decision-2026-08-26)) — ✅ answered (2026-08-27): SSO is the single source of
  truth for identity and authority; password login is a legacy path only. Most legacy
  members deliberately set their own `email` so their SSO login attaches to their
  existing account and preserves history — the current behavior is exactly the intended
  design, not a gap to close. This is also structurally safe on the admin-role question
  the original audit note raised: `is_admin` is recomputed from the token's `groups`
  claim on every login and unconditionally overwrites the local value, so an email match
  only decides which account/history a login attaches to — it never grants privilege by
  itself. No code change needed; full reasoning in the [identity-decision archive](archive/ROADMAP_AUDITS.md#docs-audit-findings-requiring-a-product-decision-2026-08-26).

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
   webhook-sync helpers — see [ARCH-01](CHANGELOG.md#2026-10-08--sprint-10-architecture-boundary-closure-arch-01) for current ownership scope) is unchanged
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
   root-causing (2026-08-27)** — full details in the [regression-diagnosis archive](archive/ROADMAP_AUDITS.md#fixed-the-4-tests-repeatedly-labeled-pre-existingenvironmental-all-session). Short version: two real template bugs in
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
     policy-blocked votes remain open (subsequently [delivered in Sprint 6](CHANGELOG.md#identity-and-vote-policy)).

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
     in the [contract-parity archive](archive/ROADMAP_AUDITS.md#error-contract-matrix-expansion).

4. **Docs synchronization pass**
   - Keep `APIDOC.md`, `SPEC.md`, `TESTING.md`, and sprint notes aligned for any contract or workflow change.

5. **Telegram-assistant reliability closure** — ✅ closed (2026-08-27).
   - Conversation history is now shared across workers (see Delivered above).
   - ✅ The end-to-end natural-language webhook contract test from the [assistant audit](CHANGELOG.md#telegram-state-and-confirmation) is
     done — see Delivered above.
   - ✅ Decided the process-local model-request queue architecture question (asked of and
     decided by the user, full reasoning in the [state/worker decision](archive/ROADMAP_AUDITS.md#shared-state-for-multi-worker-safety)): the bounded worker pool stays process-local by design, since
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
