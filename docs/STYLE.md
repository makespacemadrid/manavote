# STYLE — Engineering Principles, Dev Rules, and Delivery Guardrails

This document defines how we implement changes in this repository.

## 1) Engineering Principles

- **Stability first:** prioritize startup reliability, data integrity, and policy enforcement before feature expansion.
- **Single source of truth:** keep business rules in services/policies; avoid duplicating behavior across routes/templates/integrations.
- **Observable by default:** critical paths should emit structured logs and have testable outcomes.
- **Incremental migration:** prefer compatible, low-risk refactors over big-bang rewrites.

## 2) Implementation Recommendations

- Keep route handlers thin; orchestration belongs in route layer, business behavior belongs in services.
- Keep repository/query concerns out of route handlers whenever possible.
- Favor shared helpers or services when the same logic appears across modules.
- Preserve backward compatibility during decompositions (endpoint behavior, templates, and user-visible flows).
- For user-facing behavior changes, update i18n strings and UI copy together.

## 3) Definition of Done (Applies to All New Work)

A change is complete only when:

- Business behavior is enforced in services/policies (not route-only).
- Tests cover expected success and rejection paths.
- Logs/events include stable machine-readable fields.
- Migration/config impacts are documented.
- User-visible behavior changes are reflected in i18n and templates.
