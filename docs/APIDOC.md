# Programmatic Interface Reference

ManaVote exposes three programmatic surfaces. Each has a separate contract because its
transport, caller identity, and error model differ.

## Choose an interface

| Surface | Transport | Authentication | Reference |
|---|---|---|---|
| Admin and member REST APIs | HTTP under `/api/*` | `X-Admin-Key` for administrators; session-authenticated member tokens for member actions | [`interfaces/REST.md`](interfaces/REST.md) |
| MCP server | JSON-RPC over HTTP or legacy TCP | `MCP_API_KEY` header | [`interfaces/MCP.md`](interfaces/MCP.md) |
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

**Update only the surface file whose externally observable contract changed.** If a
change also alters product behavior, update `SPEC.md`; if it changes verification
coverage, update `TESTING.md`.

---

### Administrator Koins actions

`admin_replenish_coin_item` credits a selected member's koins and records stock
replenishment; `admin_consume_coin_item` debits their koins and records consumption.
Both accept `item` (name or ID), `member_id` (target member), `quantity` (1..1000),
and an optional `idempotency_key` for safe retries. Each unit changes both stock and
balance by one. These are ledger actions, not balance-only adjustments.

Telegram exposes these tools only to administrators and requires `/confirm` before
execution. The target member is preserved; regular member tools remain bound to the
caller's linked account. External MCP clients use the existing MCP API-key authentication.

`contribute_to_jar` (member) and `admin_contribute_to_jar` (administrator, same
confirmation/target-member rules as above) log a member's koin balance credit for
money added to the jar at a flat 1 EUR = 1 koin rate — these never collect or process
a payment, they only log a contribution that already happened. Unlike the
consume/replenish tools above, these take `amount` (1..1000 EUR). With no `item`,
the resulting ledger row has no item and never touches any item's inventory, so it's
excluded from per-item stock totals. With `item` (and optional `quantity`, default 1)
also given — e.g. paying cash for a can on the spot instead of drawing down koin
credit — the same contribution is logged together with a `consume` movement for that
item/quantity in one call; the response then has `contribution` and `consumption`
sub-objects plus a top-level `resulting_coin_balance`, rather than the flat
`{movement_id, coin_delta, resulting_coin_balance, replayed}` shape returned when no
item is given. The item is validated before the contribution is recorded.

Both accept an optional `note` (≤250 characters) and `idempotency_key`.

---

### Member Koins actions

`member_contribute_to_jar` (member) logs a member's koin balance credit for money
added to the jar at a flat 1 EUR = 1 koin rate — these never collect or process a
payment, they only log a contribution that already happened. Unlike the
admin/tools above, these take `amount` (1..1000 EUR). With no `item`, the resulting
ledger row has no item and never touches any item's inventory, so it's excluded from
per-item stock totals. With `item` (and optional `quantity`, default 1) also given —
e.g. paying cash for a can on the spot instead of drawing down koin credit — the same
contribution is logged together with a `consume` movement for that item/quantity in one
call; the response then has `contribution` and `consumption` sub-objects plus a top-level
`resulting_coin_balance`, rather than the flat `{movement_id, coin_delta, resulting_coin_balance,
replayed}` shape returned when no item is given.

`member_consume_coin_item` (member) debits their koins and records consumption.
Accepts `item` (name or ID), `quantity` (1..1000). Each unit changes both stock and
balance by one. These are ledger actions, not balance-only adjustments.

`member_set_koin_balance` (member) sets the koin balance for a specific item.
Accepts `item` (name or ID), `quantity` (any integer). Positive values increase stock
and balance; negative values decrease both. This is a ledger action.

`member_get_koin_balance` (member) returns the current koin balance for a specific
item. Accepts `item` (name or ID). Returns the current stock and balance.

---

### Member REST API (session-authenticated)

| Endpoint | Method | Description |
|---|---|---|
| `/api/members/me` | GET | Get current member profile |
| `/api/members/me/telegram` | GET | Get linked Telegram status |
| `/api/members/me/telegram`, POST | Link/unlink Telegram account |
| `/api/members/me/password` | POST | Change password |
| `/api/members/me/feedback` | POST | Submit feedback |

### Administrator REST API

| Endpoint | Method | Description |
|---|---|---|
| `/api/admin/members` | GET | List all members |
| `/api/admin/members/{id}` | GET | Get member details |
| `/api/admin/members/{id}`, POST | Update member |
| `/api/admin/koins` | POST | Administer koins (replenish/consume) |
| `/api/admin/koins/{item_id}` | POST | Administer koins for specific item |
| `/api/admin/feedback` | POST | Process feedback |
| `/api/admin/settings` | GET | Get all settings |
| `/api/admin/settings`, POST | Update settings |

---

### MCP Methods

| Method | Description |
|---|---|
| `list_user_statistics` | Get user statistics with pagination and filtering |
| `create_proposal` | Create a new proposal |
| `edit_proposal` | Edit an existing proposal |
| `delete_proposal` | Delete a proposal |
| `create_poll` | Create a new poll |
| `edit_poll` | Edit an existing poll |
| `delete_poll` | Delete a poll |
| `list_user_links` | List linked Telegram accounts |
| `link_telegram` | Link a Telegram account |
| `unlink_telegram` | Unlink a Telegram account |
| `list_user_votes` | List user votes |

---

### Telegram bot actions (webhook)

The Telegram bot processes incoming webhook updates. Key actions include:

- `/start` — Welcome message and bot introduction
- `/link` — Link Telegram account to member profile
- `/unlink` — Unlink Telegram account
- `/confirm` — Confirm a pending action
- `/cancel` — Cancel a pending action
- Vote commands — `/vote`, `/unvote` for proposals and polls
- Natural language messages — Process natural language proposals and polls

Telegram bot authentication uses the bot token and updates are validated against
the configured webhook secret.

---

### REST API Error Envelope

All REST endpoints return a consistent error envelope:

```json
{
  "error": {
    "code": "<error_code>",
    "message": "<human_readable_message>"
  }
}
```

Error codes follow this pattern:
- `-32600` — Invalid request
- `-32601` — Method not found
- `-32602` — Invalid parameters
- `-32000` — Internal application error
- `-32001` — Not found
- `-32002` — Conflict
- `-32003` — Rate limited

REST HTTP errors use the status code plus the error envelope:
- 400 — Bad request
- 401 — Unauthorized
- 403 — Forbidden
- 404 — Not found
- 409 — Conflict
- 415 — Unsupported media type
- 429 — Rate limited
- 500 — Internal server error

---

### MCP JSON-RPC Error Codes

| Code | Meaning |
|---|---|
| `-32600` | Invalid request |
| `-32601` | Method not found |
| `-32602` | Invalid parameters |
| `-32000` | Internal error |
| `-32001` | Not found |
| `-32002` | Conflict |
| `-32003` | Rate limited |

MCP errors also include a `id` field matching the request ID for correlation.

---

### Telegram Error Messages

Telegram bot messages use user-facing text, categorized by type:

- **Link errors**: "Please use /link to associate your Telegram account with your ManaVote account."
- **Vote errors**: "Your vote has been recorded." / "You cannot vote on this proposal/poll."
- **Confirmation errors**: "Action confirmed." / "Action cancelled."
- **System errors**: "An unexpected error occurred. Please try again."

Error messages are localized and should not be parsed programmatically; use error
codes instead.

---

## Surface-specific guidelines

### REST API

- All endpoints under `/api/*`
- Authentication: `X-Admin-Key` for admins, session tokens for members
- Rate limiting: 100 requests/minute per IP; 1000 requests/minute per admin key
- Versioning: None currently; backward compatibility is maintained indefinitely

### MCP server

- JSON-RPC 2.0 over HTTP or TCP
- Authentication: `MCP_API_KEY` header
- Rate limiting: 60 requests/minute per key
- Versioning: None currently; maintain backward compatibility

### Telegram bot

- Updates via webhook POST
- Secret validation as configured in `.env`
- Rate limiting: Per-user, per-chat limits apply
- Versioning: None currently; maintain backward compatibility

---

## Changing an interface

When modifying any interface:

1. Update the surface file whose contract changed
2. If product behavior changes, update `SPEC.md`
3. If verification coverage changes, update `TESTING.md`
4. Update any dependent documentation in `DIAGRAMS.md`
5. Add or update test cases in `TESTING.md`
6. Do not duplicate payload schemas across documents — link instead

---

## Version compatibility policy

- **Backward compatibility is maintained indefinitely** for all surfaces
- **Breaking changes** are announced at least one sprint in advance
- **Deprecation** is marked in the surface file and `CHANGELOG.md`
- **Removed features** are tracked in `IDEAS.md` and `CHANGELOG.md`

---

## Discovery

New developers should start with `QUICKSTART.md`, then explore
`SPEC.md` for product behavior, and `APIDOC.md` for interface details.
`OPERATIONS.md` covers production operations, and `TESTING.md` covers verification.</think>
<tool_call>
<function=shell>
<parameter=command>
cd /home/coder/Projects && wc -l docs/APIDOC.md