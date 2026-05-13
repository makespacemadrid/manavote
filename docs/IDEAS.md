# IDEAS — Forward Roadmap

Last updated: 2026-05-13

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
4. Operations become diagnosable (structured events, key counters, backup confidence).

---

## Workstreams & Backlog

## Recent audit notes (2026-05-13)

Audit scope focused on Telegram-link diagnostics/parity paths and adjacent reliability surfaces.

### Confirmed strengths
- REST and MCP member-link diagnostics now share one canonical SQL classification helper (`app/services/telegram_link_diagnostics.py`), reducing drift risk.
- REST/MCP parity tests now cover both success shape and invalid pagination bounds for Telegram member-link listing.

### Follow-up gaps to prioritize
1. **Route exception granularity (P0)**
   - Several route handlers still use broad `except Exception` blocks and generic failure messages.
   - Introduce typed exceptions + reason-code mapping for predictable operator diagnostics.

2. **MCP extraction boundary (P1)**
   - MCP still embeds substantial SQL/business rules inline.
   - Extract MCP query/use-case logic into service/repository modules shared with REST where feasible.

3. **Query fragment safety/readability (P1)**
   - Shared SQL snippets are centralized, but still string-composed.
   - Add a small query-builder utility for reusable fragments and predictable formatting/validation.

4. **Error-contract matrix expansion (P1)**
   - Extend parity coverage beyond voting + telegram listing:
     - proposal create/update validation edges,
     - poll creation bounds,
     - pagination/type errors across list endpoints.

5. **Observability completion for Telegram lifecycle (P2)**
   - Add reason-coded audit events for link/unlink operations and blocked votes by policy mode.
   - Expose `last_linked_at`/`last_unlinked_at` metadata for admin diagnostics.

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

### C3. Proposal lifecycle state machine
- Centralize legal transitions.
- Return stable error codes for illegal transitions.

### C4. Query/index optimization pass
- Add indexes for high-frequency filters/lookups.
- Capture before/after query plans for key endpoints.

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
- Keep blocked-channel guidance consistent across dashboard, proposal detail, and Telegram responses.
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
- Add a compact behavior matrix test suite across dashboard, proposal detail, polls, and Telegram webhook flows.

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
