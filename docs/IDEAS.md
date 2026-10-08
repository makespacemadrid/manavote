# IDEAS — Forward Roadmap

Last reviewed: 2026-10-08

This is the backlog of unfinished work. Each item has a stable ID, a concrete outcome,
and a completion signal. [SPRINTS.md](SPRINTS.md) owns scheduled scope and status;
[CHANGELOG.md](CHANGELOG.md) preserves completed ideas and historical audit evidence.
Current behavior and contracts belong in [SPEC.md](SPEC.md) and [APIDOC.md](APIDOC.md).

## Priorities and scheduling

| Priority | Item | Disposition |
|---|---|---|
| P1 | API-01 / API-02: remaining contracts and lifecycle rules | Sprint 16: existing REST/MCP proposal-creation contracts, REST edit compatibility, and purchase/deletion/withdrawal/edit transaction safety; Sprint 13 read and approval/undo protections remain delivered |
| P2 | OPS-01 / OPS-02: bootstrap and key rotation | Sprint 17: secure development bootstrap and active/next REST/MCP keys; retrieval and rollout decisions precede implementation |
| P2 | BOT-05 / BOT-07: history lifecycle and interaction | Sprint 18: retention/deletion and selected deterministic status/localization gaps; policy and in-flight ownership decisions required |
| P2 | OPS-04 / DATA-01 / selected OPS-03: recovery and measurements | Sprint 19: consistent/readable backups, recency health and safe backup events, representative query measurements; optimizations require evidence |
| P2 | UX-03 / UX-04: proposal and budget usability | Sprint 20: search/filter/sort and chart series controls; task feedback and interaction defaults precede implementation |
| P2 | BOT-04 / remaining OPS-03 / DATA-02 | Unscheduled: running-call interruption, general REST telemetry, and new participation analytics require supported cancellation or a concrete operator workflow |

Sprints 12–15 are complete. Sprints 16–20 are planned for sequential execution, with
dependencies, decision gates, deferred scope, and acceptance checks in
[SPRINTS.md](SPRINTS.md). Scheduling a slice does not imply that the whole backlog
item is complete. Keep remaining scope here until its completion signal is met.

Completed architecture, assistant-safety/health, vote-coverage, and bounded UX outcomes
from Sprints 10–15 live in [CHANGELOG.md](CHANGELOG.md).
P0 protects core correctness; P1 addresses concrete safety, contract,
or accessibility gaps; P2 needs usage or operational evidence before expansion.
Planned P2 sprints include discovery and policy gates; scheduling does not assert that
those decisions or measurements already exist.
Priority does not authorize a broad rewrite. Follow [STYLE.md](STYLE.md), preserve
compatibility, and choose the smallest slice with a testable outcome.

## Architecture and API contracts

### API-01 — Protect request/response contracts (P1)

Select a high-value endpoint/tool pair and define inbound validation and outbound
field/type guarantees. Add compatibility checks for accidental field removal or type
changes. Keep the delivered REST error envelope and MCP JSON-RPC envelope intact.

**Done when:** the selected contract has success and rejection coverage and a canonical
field definition in the surface references linked from APIDOC; other endpoints can
follow in independently scoped slices. Sprint 13 delivered checks for `GET /api/proposals` and MCP
`list_proposals`; select a different demonstrated contract gap for the next slice.

### API-02 — Centralize proposal lifecycle transitions (P1)

Sprint 10 already placed proposal actions and processing in services. Inventory their
existing approval, rejection, purchase, undo, and deletion behavior before consolidating
transition validation within those owners. Sprint 13 delivered shared approval/over-budget validation, serialized undo, retry/concurrency
safety, and ledger rollback checks. The lifecycle/permission matrix is documented in SPEC;
select another transition only when a concrete validation gap warrants it. Preserve
documented permissions and compatibility; record intentional web/API differences and
agree policy changes explicitly rather than hiding them in a refactor.

**Done when:** the selected lifecycle operations share transition validation and tests
cover allowed/rejected transitions, permissions, and budget side effects.

### DATA-01 — Measure statistics and list-query performance (P2)

Capture query plans and timings for correlated statistics queries and proposal-age
filters using representative row counts. Add indexes or rewrite queries only when the
measurements show a benefit. Statistics pagination already exposes both page `count`
and matching `total`; this does not imply that every list contract has those fields.

**Done when:** before/after plans and timings justify the selected change and response
shape, ordering, pagination, and lifetime semantics remain covered by regression tests.

### DATA-02 — Evolve participation analytics from admin workflows (P2)

Evaluate optional date windows and additional aggregate views only for a concrete
operator question. Keep lifetime statistics as the default, administrator-only access,
minimal identity fields, and opt-in email exposure. Existing sorting and pagination
totals are delivered foundations, not new scope.

**Done when:** the selected workflow has agreed semantics, documented inputs/outputs,
and matching REST/MCP authorization and contract tests.

## Telegram assistant

### BOT-04 — Cancel running model work safely (P2)

Sprint 15 delivered owned queued-job cancellation through `/cancel`, including admission
bypass, pending-action ownership, accurate running status, race-safe cleanup, and
process-local operator health. Remaining work is safe interruption of running model/HTTP
calls when the client supports it. Define suppression of stale replies and handle tool
execution races without claiming that a committed action can be undone. Distributed
cancellation is a separate infrastructure decision.

**Done when:** supported running-call interruption has ownership/race tests, releases
capacity only when execution actually ends, and returns accurate cancellation outcomes.

### BOT-05 — Define durable-history retention and deletion (P2)

Conversation history already resides in SQLite. Agree retention, expiry, deletion, and
operator-access rules; do not describe it as ephemeral. Keep contents out of telemetry.

**Done when:** policy is documented and expiry/deletion tests cover persisted history
without affecting pending-confirmation integrity or webhook retry records.

### BOT-07 — Improve assistant status and localization (P2)

Busy/retry replies already support English and Spanish. Evaluate typing indicators or
edits to the temporary status message and localize the remaining deterministic assistant
messages. Preserve cleanup/delivery behavior across failures; translating new Sprint 12
or 15 messages does not complete this broader interaction audit.

**Done when:** the selected interaction works in English/Spanish and tests cover long
responses, missing status messages, and transport errors.

## Security and operations

| ID | Priority | Outcome | Completion signal |
|---|---|---|---|
| OPS-01 | P2 | Replace the static development bootstrap-password fallback with a one-time generated-secret flow | Fresh bootstrap, existing accounts, and production refusal rules are tested; secure retrieval and migration are documented |
| OPS-02 | P2 | Support API-key rotation with overlapping active/next keys | Old/new key acceptance and retirement are tested without logging credentials |
| OPS-03 | P2 | Extend safe request/event and throughput/error/latency metrics beyond the assistant health delivered in Sprint 15 | Select another demonstrated operator need; critical paths expose safe request, endpoint, status, latency, and reason metadata with useful runbook interpretations |
| OPS-04 | P2 | Verify backup recency and readability against an agreed recovery-point objective | Stale/unreadable backups yield health signals; healthy backups and verification failures are tested without modifying live data |

## Member and administrator UX

The remaining findings were checked against code on 2026-10-08. Legacy audit numbers
refer to the original findings preserved in CHANGELOG; they are provenance, not priority.

| ID | Priority | Remaining problem / outcome | Completion signal |
|---|---|---|---|
| UX-03 | P2 | Proposal status and size filter chips compete; no search/sort (audits 12, 27) | An agreed filter/search/sort interaction preserves selected state, server filtering, and usable mobile navigation |
| UX-04 | P2 | Six budget datasets are dense; legend-only series toggling is hard to discover (audit 15) | A clear series/density control complements the existing date-range control and labelled table filters |

## Discovery before broader UX work

Use current feedback to identify casual-member, power-member, and operator journeys
(first vote, Telegram linking, Koins replenishment, admin maintenance). Prioritize
observed friction before expanding navigation, Admin/Settings boundaries, page context
headers, or form microcopy. Extend shared tokens/components where repeated markup
justifies it, and verify keyboard access, contrast, responsive layouts, and translations.

Promote a discovery item into scheduled scope only when it has a concrete problem,
proposed outcome, and verification plan. Completed delivery moves to CHANGELOG; do not
reintroduce shipped confirmations, feedback, chart ranges, or admin tabs as new work.
