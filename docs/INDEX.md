# Documentation Index

Use this page as the entry point for project documentation.

## Start here

- **Quick start / deployment**: [`QUICKSTART.md`](QUICKSTART.md)
- **Technical behavior contract**: [`SPEC.md`](SPEC.md)
- **REST API + MCP reference**: [`APIDOC.md`](APIDOC.md)
- **Testing commands and coverage map**: [`TESTING.md`](TESTING.md)
- **Operations, logs, and troubleshooting**: [`OPERATIONS.md`](OPERATIONS.md)
- **Architecture diagrams**: [`DIAGRAMS.md`](DIAGRAMS.md)

## Engineering process

- **Implementation standards & guardrails**: [`STYLE.md`](STYLE.md)
- **Backlog / ideas**: [`IDEAS.md`](IDEAS.md)
- **Sprint tracking**: [`SPRINTS.md`](SPRINTS.md)
- **Retrospective — lessons from this project's own history**: [`META.md`](META.md)

## Which doc should I update?

- Update **`SPEC.md`** for behavior changes (routes, rules, integration flows).
- Update **`APIDOC.md`** for API request/response contract changes.
- Update **`QUICKSTART.md`** for setup/runtime configuration changes.
- Update **`TESTING.md`** when new regression packs or testing workflows are added.
- Update **`OPERATIONS.md`** for reason codes, structured logs, startup health, backup
  lifecycle, and production troubleshooting.
- Update **`DIAGRAMS.md`** in the same change that alters a flow it depicts (routing,
  the confirm state machine, startup sequence, or the data model) — a diagram that
  disagrees with the code is worse than no diagram.
