# Roadmap — Pending Priorities

**Status:** alpha — living document, moved to `IDEAS.md` item once scheduled.

**MECE alignment:** This file is Mutually Exclusive and Collectively Exhaustive
with respect to `IDEAS.md` (backlog) and `SPRINTS.md` (scheduled scope). Items
promoted to scheduled status are removed from this file and tracked in
`SPRINTS.md`; completed items move to `CHANGELOG.md`.

## Legend

| Symbol | Meaning |
|---|---|
| `P0` | Core correctness or safety — must fix before release |
| `P1` | Concrete gap affecting usability, contracts, or accessibility |
| `P2` | Operational or policy evidence needed before expansion |
| `→` | Item is scheduled in a future sprint |
| `🔒` | Blocked by external decision/dep |

---

## P0 — Core Correctness & Safety

- [ ] **API contract completeness** — Ensure all REST/MCP endpoints have exhaustive
  request/response schemas and error-handling guards. *Blocked until Sprint 16
  delivery.*
- [ ] **Purchase withdrawal safety** — Verify that withdrawal/deletion transactions
  cannot corrupt `group_purchase_quantities` or `group_purchase_payments` states.
  *Blocked until Sprint 16.*

---

## P1 — Usability & Accessibility Gaps

- [ ] **Proposal validation UX** — Member task validation for proposal creation
  (member limits, budget checks). *Delivered in PRs #127–128; remaining scope
  tracked here.*
- [ ] **Budget threshold adjustments** — Update `threshold_default`, `threshold_over50`,
  `threshold_basic` values based on recent transaction data. *P2; requires
  evidence.*
- [ ] **Localized error messages** — Add Spanish translations for all P1/P2 error
  paths in the web interface and Telegram notifications. *P2.*

---

## P2 — Operational & Policy Evidence

- [ ] **Backup recency health** — Define and publish a monthly “backup health score”
  (last successful backup, bytes backed up, verification status). *Sprint 19:*
  consistent/readable backups, recency health and safe backup events.
- [ ] **Participation analytics** — New endpoint/query for tracking participation
  trends across group purchases, proposals, and polls. *Unscheduled: requires a
  cancellation workflow or concrete operator flow.*
- [ ] **Key rotation procedure** — Document and test the active/next REST/MCP key
  rollover process. *Sprint 17: secure development bootstrap and active/next
  REST/MCP keys.*
- [ ] **History lifecycle** — Retention/deletion policies for bot interaction
  history, with deterministic status/localization gaps. *Sprint 18.*
- [ ] **Review 2026-11-23 test baseline audit findings** — 19 failures across
  `test_proposal_image_validation` (stale past-date fixture) and
  `test_documentation` (missing doc anchors in OPERATIONS.md / IDEAS.md); none are
  code regressions. Fix the test fixture date and add the missing anchors, then
  consider promoting to a scheduled item if operator-facing test-health evidence is
  needed. See `docs/archive/ROADMAP_AUDITS.md#test-baseline-audit-2026-11-23`.

---

## → Scheduled (Sprints 16–19)

| Sprint | Priority | Item | Disposition |
|---|---|---|---|
| 16 | P1 | API-01 / API-02: remaining contracts and lifecycle rules | REST/MCP proposal-creation, edit compatibility, purchase/deletion/withdrawal/edit safety |
| 16 | P2 | OPS-01 / OPS-02: bootstrap and key rotation | Secure dev bootstrap and active/next REST/MCP keys |
| 17 | P2 | BOT-05 / BOT-07: history lifecycle and interaction | Retention/deletion and selected deterministic status/localization gaps |
| 18 | P2 | OPS-04 / DATA-01 / selected OPS-03: recovery and measurements | Consistent/readable backups, recency health, safe backup events, measurements |
| 19 | P2 | UX-03 / UX-04: proposal and budget usability | Member task validation and representative query measurements |
| 19 | P2 | BOT-04 / remaining OPS-03 / DATA-02 | Running-call interruption, general REST telemetry, participation analytics |

---

## 📋 Completed (reference)

Completed architecture, assistant-safety/health, vote-coverage, and bounded UX
outcomes from Sprints 10–15 live in [`CHANGELOG.md`](CHANGELOG.md).

P0 protects core correctness; P1 addresses concrete safety, contract, or
accessibility gaps; P2 needs usage or operational evidence before expansion.

---

## Source-of-truth rules (aligned with `docs/INDEX.md`)

| Information | Canonical owner | This file’s role |
|---|---|---|
| Environment variable names and setup steps | `QUICKSTART.md` | Link to relevant headings; not duplicated here |
| User-visible behavior and business rules | `SPEC.md` | Items here reflect gaps vs. current behavior |
| Request/response fields, tool inputs, and API errors | `APIDOC.md` | Items reflected as P1/P2 gaps |
| Commands for tests and what each suite proves | `TESTING.md` | Not duplicated; gaps noted as P2 |
| Production checks and incident response | `OPERATIONS.md` | Not duplicated; gaps noted as P2 |
| Diagrammed flows | `DIAGRAMS.md` | Not duplicated; gaps noted as P2 |
| Coding and delivery policy | `STYLE.md` | Not duplicated |
| Uncommitted future work | `IDEAS.md` | This file is the *pending* subset; items promoted here become sprint candidates |
| Shipped roadmap outcomes | `CHANGELOG.md` | Items removed from this file once delivered |
| Detailed historical audits and decisions | `archive/ROADMAP_AUDITS.md` | Not duplicated; reference only |
| Iteration scope, status, and sprint history | `SPRINTS.md` | Items promoted from here are removed from this file |

### Precedence when scopes touch

1. The code and database migrations define what the application actually does.
2. `SPEC.md` defines the intended product and domain behavior.
3. `APIDOC.md` defines the externally observable wire contract.
4. `QUICKSTART.md` and `OPERATIONS.md` define how to configure and operate it.
5. `TESTING.md` explains how that behavior is verified.
6. `DIAGRAMS.md` is explanatory; if it disagrees with a normative document, update the diagram.

### Quick routing examples

- A new API field: document its wire contract in `APIDOC.md`; document any new
  product behavior in `SPEC.md`; add the verification command only to `TESTING.md`.
- A new environment flag: define it in `QUICKSTART.md`; describe operational failure
  signals in `OPERATIONS.md` only if operators can act on them.
- A proposed feature: record it in `IDEAS.md`, not `SPEC.md`. Once implemented,
  describe the resulting behavior in `SPEC.md`, move the idea to `CHANGELOG.md`,
  and retain its sprint execution record in `SPRINTS.md`. Items promoted from
  `IDEAS.md` to scheduled status move into this file; once delivered, they move to
  `CHANGELOG.md` and are removed from this file.

---

## How to Use This File

1. **Review each quarter** — promoted items become sprint candidates.
2. **Move completed items** to `CHANGELOG.md` with a completion date.
3. **Promote P2 → P1** when there is operational evidence.
4. **New items** should be added to `IDEAS.md` with a stable ID, then promoted
   here when ready for scheduling.
5. **Items removed** from this file (promoted or completed) should have their
   ID referenced in `SPRINTS.md` or `CHANGELOG.md` for audit trail.

*This file is MECE with respect to `IDEAS.md` (backlog) and `SPRINTS.md`
(scheduled scope). Items must not appear in both this file and `SPRINTS.md`
simultaneously; items must not appear in both this file and `IDEAS.md` unless
they are explicitly pending scheduling.*