# Programmatic Interface Reference

ManaVote exposes three programmatic surfaces. Each has a separate contract because its
transport, caller identity, and error model differ.

## Choose an interface

| Surface | Transport | Authentication | Reference |
|---|---|---|---|
| Admin and member REST APIs | HTTP under `/api/*` | `X-Admin-Key`, except session-authenticated member feedback | [`interfaces/REST.md`](interfaces/REST.md) |
| MCP server | JSON-RPC over HTTP or legacy TCP | `MCP_API_KEY` | [`interfaces/MCP.md`](interfaces/MCP.md) |
| Telegram bot | Telegram webhook updates | Linked Telegram identity; role checks vary by action | [`interfaces/TELEGRAM.md`](interfaces/TELEGRAM.md) |

## Scope boundaries

- Product behavior and business rules belong in [`SPEC.md`](SPEC.md).
- Environment variables and setup belong in [`QUICKSTART.md`](QUICKSTART.md).
- Executable verification commands belong in [`TESTING.md`](TESTING.md).
- Production diagnostics and incident response belong in
  [`OPERATIONS.md`](OPERATIONS.md).

## Shared contract principles

- REST errors use an HTTP status plus a nested `error.code` and `error.message` object.
- MCP errors use JSON-RPC error codes and envelopes.
- Telegram presents user-facing messages while enforcing the same service-layer rules
  as REST and MCP.
- Authentication is surface-specific; credentials are never interchangeable between
  REST, MCP, and Telegram.

Update only the surface file whose externally observable contract changed. If a change
also alters product behavior, update `SPEC.md`; if it changes verification coverage,
update `TESTING.md`.


### Administrator Koins actions

`admin_replenish_coin_item` credits a selected member's koins and records stock
replenishment; `admin_consume_coin_item` debits their koins and records consumption.
Both accept `item` (name or ID), `member_id` (target member), `quantity` (1..1000),
and an optional `idempotency_key` for safe retries. Each unit changes both stock and
balance by one. These are ledger actions, not balance-only adjustments.

Telegram exposes these tools only to administrators and requires `/confirm` before
execution. The target member is preserved; regular member tools remain bound to the
caller's linked account. External MCP clients use the existing MCP API-key authentication.
