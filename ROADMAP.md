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


## 📋 Completed (reference)

Completed architecture, assistant-safety/health, vote-coverage, and bounded UX
outcomes from Sprints 10–15 live in [`CHANGELOG.md`](CHANGELOG.md).

P0 protects core correctness; P1 addresses concrete safety, contract, or
accessibility gaps; P2 needs usage or operational evidence before expansion.

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