# Documentation Map

This is the canonical entry point for ManaVote documentation. The documentation is
organized by **reader intent**, so each question has one primary home. Supporting
documents link to that home instead of repeating its content.

## Use the docs by task

| If you want to… | Read | Scope |
|---|---|---|
| Install, configure, or upgrade ManaVote | [`QUICKSTART.md`](QUICKSTART.md) | Prerequisites, first run, environment variables, and deployment setup |
| Understand what the product does | [`SPEC.md`](SPEC.md) | Current behavior, business rules, routes, data model, and security constraints |
| Integrate another system | [`APIDOC.md`](APIDOC.md) | REST, MCP, and Telegram authentication, contracts, examples, and error semantics |
| Run or extend automated checks | [`TESTING.md`](TESTING.md) | Test commands, suites, and coverage responsibilities |
| Diagnose a running installation | [`OPERATIONS.md`](OPERATIONS.md) | Health, logs, backups, reason codes, and incident checks |
| Understand a system flow visually | [`DIAGRAMS.md`](DIAGRAMS.md) | Architecture, request, startup, Telegram, and data-flow diagrams |
| Contribute code consistently | [`STYLE.md`](STYLE.md) | Engineering rules, delivery guardrails, and definition of done |

Together these seven documents cover the current system. The first five own distinct
facts—**setup**, **behavior**, **interfaces**, **verification**, and **operation**.
The last two are supporting views: diagrams explain those facts visually, while the
style guide governs how contributors change them. Supporting views are never the
normative source for runtime behavior.

## Planning and historical records

The following files are not current-system reference material. They answer separate
questions about future work or past decisions:

| Question | Read | Document status |
|---|---|---|
| What might we build next? | [`IDEAS.md`](IDEAS.md) | Forward-looking backlog and audit findings |
| What was delivered in each iteration? | [`SPRINTS.md`](SPRINTS.md) | Chronological execution record |
| What did the project teach us? | [`META.md`](META.md) | Retrospective and generalized lessons |
| What is the Koins design history? | [`COINS_PLAN.md`](COINS_PLAN.md) | Feature-specific plan; implemented behavior belongs in `SPEC.md` |

Planning documents may preserve historical context that no longer matches the live
application. When they conflict with a current-system document, the current-system
document is authoritative.

## Source-of-truth rules

Use this ownership table to prevent the same fact from drifting across files.

| Information | Canonical owner | Other docs should… |
|---|---|---|
| Environment variable names and setup steps | `QUICKSTART.md` | Link to the relevant heading |
| User-visible behavior and business rules | `SPEC.md` | Summarize only when needed, then link |
| Request/response fields, tool inputs, and API errors | `APIDOC.md` | Link rather than copy payloads |
| Commands for tests and what each suite proves | `TESTING.md` | Include only the shortest smoke command, if essential |
| Production checks and incident response | `OPERATIONS.md` | Link rather than duplicate runbooks |
| Diagrammed flows | `DIAGRAMS.md` | Keep prose normative; diagrams remain explanatory |
| Coding and delivery policy | `STYLE.md` | Avoid restating it in plans |
| Uncommitted future work | `IDEAS.md` | Move it to `SPRINTS.md` only when scheduled |
| Iteration status and delivery history | `SPRINTS.md` | Keep it out of reference docs |

### Precedence when scopes touch

Some changes necessarily affect several documents. That is not duplication when each
document records a different aspect of the change:

1. **The code and database migrations** define what the application actually does.
2. **`SPEC.md`** defines the intended product and domain behavior.
3. **`APIDOC.md`** defines the externally observable wire contract.
4. **`QUICKSTART.md` and `OPERATIONS.md`** define how to configure and operate it,
   respectively.
5. **`TESTING.md`** explains how that behavior is verified.
6. **`DIAGRAMS.md`** is explanatory; if it disagrees with a normative document, update
   the diagram.

For example, an API-backed feature can legitimately appear in `SPEC.md`, `APIDOC.md`,
and `TESTING.md`, but the product rule, payload schema, and verification command should
appear only in their respective owners.

## Updating documentation

1. **Choose one owner** from the table above for the full explanation.
2. **Update related links**, not duplicate prose, in other documents.
3. **Keep time-bound content out of reference docs**: planned work goes in
   `IDEAS.md`, and scheduled/completed work goes in `SPRINTS.md`.
4. **Update diagrams with the code change** when routing, confirmation state,
   startup sequence, or the data model changes.
5. **Update tests documentation with the test change** when a suite is added,
   removed, renamed, or given a new responsibility.

## Quick routing examples

- A new API field: document its wire contract in `APIDOC.md`; document any new
  product behavior in `SPEC.md`; add the verification command only to `TESTING.md`.
- A new environment flag: define it in `QUICKSTART.md`; describe operational failure
  signals in `OPERATIONS.md` only if operators can act on them.
- A proposed feature: record it in `IDEAS.md`, not `SPEC.md`. Once implemented,
  describe the resulting behavior in `SPEC.md` and preserve delivery history in
  `SPRINTS.md`.
