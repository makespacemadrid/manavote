# MCP Reference

This document owns ManaVote's Model Context Protocol contract: transports,
authentication, tool inputs and outputs, and JSON-RPC errors. For product rules, see
[`../SPEC.md`](../SPEC.md); for other integration surfaces, return to the
[interface index](../APIDOC.md).

## Contents

- [Authentication](#authentication)
- [Run modes](#run-modes)
- [Implemented tools](#implemented-mcp-tools)
- [Error conventions](#mcp-error-code-conventions)
- [Request example](#example-mcp-request)
- [Create-proposal example](#example-mcp-create-request-create_proposal)

The project also exposes an MCP JSON-RPC server (`app/mcp_server.py`) for admin tooling.

## Authentication
- Configure `MCP_API_KEY` in environment.
- Every MCP request (except `notifications/initialized`) must authenticate with one of:
  - `X-Api-Key: <MCP_API_KEY>` HTTP header (recommended), or
  - `Authorization: Bearer <MCP_API_KEY>` HTTP header, or
  - `params.api_key: <MCP_API_KEY>` in JSON-RPC body (legacy compatibility).

If key is missing/invalid, server responds with JSON-RPC error code `-32001` and message:
`Unauthorized: invalid or missing MCP api_key`.

## Copy tools

`copy_proposal`, `copy_poll`, and `copy_group_purchase` accept required positive integer
`source_id` and `created_by`. These are admin actions through authenticated MCP; in the
Telegram assistant they require administrator confirmation and bind `created_by` to the
linked administrator rather than trusting model-supplied attribution.

- `copy_proposal`: optionally override `title` and `deadline` (future ISO datetime with timezone). Copies description, amount, product URL,
  basic-supplies flag (subject to the €20 rule), and an independent local image. Starts
  active with no votes, comments, approval/purchase timestamps, or budget/ledger changes.
- `copy_poll`: optionally override `question` and `deadline`. Copies options and multiple-
  selection setting; starts open without votes. Old deadlines are cleared. A supplied
  deadline must be a future ISO datetime with timezone (normalized to UTC for scheduling).
- `copy_group_purchase`: optionally override `title` and `deadline` (current/future
  YYYY-MM-DD). Copies description, product URL, image, payment instructions, components/
  prices, shared-cost definitions, member limit and €125-cap setting. Component IDs are
  new; quantities, participants, payment receipts and old deadline are not copied. New
  purchases obey current creation/closing limits, so shared costs alone reaching a copied
  cap can immediately close joining.

Example tool arguments: `{"source_id":42,"created_by":7,"title":"Next month's order"}`
for `copy_group_purchase`. Other override fields are rejected. Success returns `success`,
`source_id`, the new `proposal_id`/`poll_id`/`group_purchase_id`, and `warnings`.
Missing source/creator returns `-32004`, invalid inputs `-32602`, and storage failures
`-32012`. Copying is transactional and does not modify the source. Fresh copies queue a Telegram announcement through the shared backend; web, REST and Telegram-assistant copies behave identically. Replayed requests do not announce again.
Copy tools accept optional `idempotency_key` (1–128 letters, digits, dots, underscores,
colons or hyphens). Retrying the same key and arguments returns the saved result with
`replayed: true`; initial success includes `replayed: false`. Reusing a key with different
arguments, or replaying a copy that was deleted, returns `-32009`. Keys are scoped to
the new creator across copy tools. Without an explicit key, identical arguments reuse
their original result; supply a fresh key for another intentional identical copy.
The durable request record, new item and image lifecycle share the same transaction,
so concurrent retries cannot create duplicates. Images are independently
duplicated; a missing source image is omitted with a warning. New images are removed
when a transaction fails.

## Run modes
1. **Standalone stdio**
```bash
python -m app.mcp_server
```

2. **Alongside Flask app (HTTP)**
Set environment variables:
- `MCP_SERVER_ENABLED=true`
- `MCP_SERVER_TRANSPORT` (optional, default `http`; set `tcp` for legacy transport)
- `MCP_SERVER_HOST` (optional, default `0.0.0.0` — binds all interfaces; set `127.0.0.1` to restrict to localhost)
- `MCP_SERVER_PORT` (optional, default `8765`)

Then start app normally (`python app.py`).
The JSON-RPC endpoint is `POST http://<host>:<port>/mcp` and health check is `GET /healthz`.
The HTTP endpoint supports JSON-RPC single and batch request payloads.

## Implemented MCP tools
- `list_proposals`
  - optional args: `proposal_id` (exact positive integer ID), `status` (`active|approved|over_budget|rejected`), `age` (`recent|old`), `username` (exact, case-insensitive creator match), `limit` (1..200), `offset` (>=0)
  - `age=recent` returns active proposals newer than 30 days; `age=old` returns active proposals at least 30 days old. It may only be combined with `status=active`.
  - out-of-range pagination and invalid proposal IDs are rejected with `-32602`; values are not silently clamped.
  - each proposal includes its persisted external reference `url` and local
    `image_filename`, plus public `proposal_url` and `image_url` fields derived from the
    Base URL configured in Admin → Telegram Configuration. Public fields are `null` when
    the Base URL is unset; `image_url` is also `null` when the proposal has no image.
    Telegram natural chat can return all three links: it uses `url` when a member asks
    for the listed/vendor/reference link and labels it separately from the ManaVote
    proposal and image links. When the assistant includes a returned `image_url` in its
    answer, the Telegram adapter also sends that URL through Telegram's `sendPhoto`, so
    the image appears as media as well as remaining available as a clickable link.
- `list_polls`
  - optional args: `status` (`open|closed`), `username` (creator match), `limit`, `offset`
  - returns each poll's options, `allow_multiple` flag, and per-option vote results
- `list_group_purchases`
  - optional args: `status`, `username`, `limit`, `offset`
  - returns components, shared costs, and per-participant amounts owed/paid
- `current_budget`
- `list_coin_items`
  - optional `member_id`; returns Coke, Coke Zero, and Other Can with current stock and
    the member's aggregate ManaVote koin balance when a member is supplied
- `list_coin_movements`
  - optional `item`, `member_id`, `limit` (1..200), and `offset`; returns newest ledger
    movements first
  - Telegram always binds `member_id` to the linked sender, so members only retrieve
    their own movement history through the bot
- `consume_coin_item`
  - required `item` (case-insensitive name or positive ID) and `member_id`; optional
    `quantity` (defaults to 1) and `idempotency_key`
  - removes stock and debits one ManaVote koin per can
- `replenish_coin_item`
  - required `item`, `member_id`, and `quantity`; optional `idempotency_key`
  - adds stock and credits one ManaVote koin per can
  - Telegram binds `member_id` to the linked sender for both write tools, so the model
    cannot record a movement for another member
- `list_user_statistics` (optional `limit` from 1..500, `offset` >= 0, `username`, sorting fields, and `include_email`)
  - returns the same per-user participation fields as `GET /api/members/statistics`
  - returns page `count` and matching `total`; email is opt-in and defaults to omitted
- `list_member_telegram_links` (optional `include_unlinked`, `limit`, `offset`)
  - result rows include `linked`, `link_state` (`linked|missing_user_id|unlinked`), and
    `last_linked_at`/`last_unlinked_at` — see the definitions under
    `GET /api/members/telegram` above
  - `limit` validation: must be between `1` and `500`
  - invalid boolean values for `include_unlinked` are rejected with `-32602`
- `get_voting_settings`
- `update_voting_settings`
  - optional args: `poll_vote_mode` (`both|web_only|telegram_only`), `proposal_vote_mode` (`both|web_only|telegram_only`), `telegram_require_linked_vote` (`true`/`false`)
- `create_member`
  - required args: `username`, `password`
  - optional args: `is_admin` (`true`/`false`)
- `create_proposal`
  - required args: `title`, `amount` (>0), `created_by` (existing member id) — a
    non-positive or otherwise unmatched `created_by` is rejected with `-32004` (not
    found), matching REST and `create_poll`, not `-32602`
  - optional args: `description`, `url`, `basic_supplies` (must parse as boolean;
    an unrecognized value is rejected with `-32602`, matching REST's
    `invalid_basic_supplies`), and `image`
  - `image` accepts a base64 data URL, a raw base64 string, or an object containing
    `data` plus optional `mime_type`. Only signature-validated PNG/JPEG content up to
    10 MiB is accepted. Invalid encoding, size, type, or MIME/content mismatches return
    `-32602` without creating a proposal.
  - successful results include `proposal_id`, the persisted `url`, and the generated
    local `image_filename` (or `null` when no image was supplied)
- `create_poll`
  - required args: `question` (5..200 characters), `options` (2..12 items), `created_by` (existing member id)
  - optional args: `allow_multiple` (`true`/`false`, defaults to `false`; must parse
    as boolean, an unrecognized value is rejected with `-32602`); fixed for the
    poll's lifetime once created (see SPEC.md's "Multi-select polls")
  - on success, announces the poll to the configured Telegram chat (inline "Vote"
    button) using the same message the web form and `POST /api/polls` send; the
    announcement always uses `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`/
    `TELEGRAM_THREAD_ID` from the environment, independent of the MCP caller
  - successful results include `allow_multiple` reflecting what was created

Natural-language Telegram members (non-administrators) receive the read-only tools:
`list_proposals`, `list_polls`, `list_group_purchases`, `current_budget`, and
`get_voting_settings`. Administrators additionally receive the write/statistics tools
above (except `create_member`, which is excluded from Telegram entirely).

`create_proposal`'s misspelled historical alias `crreate_proposal` is still accepted and
routed to `create_proposal`; a successful call through the alias includes a `warning`
field in its response.

## MCP error code conventions
- `-32602`: invalid params / validation failures (bad types, missing fields, range/length constraints). JSON-RPC `params` and tool `arguments` must be objects when provided.
- `-32010`: conflict class errors (currently used for duplicate member username)
- `-32011`: conflict class errors from a database integrity error (for example `create_proposal`)
- `-32012`: unavailable class errors from a database operational error
- `-32004`: not found class errors (for example missing `created_by` member)
- `-32001`: authentication failures (`MCP_API_KEY` missing/invalid)

MCP regression command:
```bash
pytest -q tests/test_mcp_server.py
```

## Example MCP request
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "api_key": "your_mcp_api_key",
    "name": "current_budget",
    "arguments": {}
  }
}
```

## Example MCP create request (`create_proposal`)
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "api_key": "your_mcp_api_key",
    "name": "create_proposal",
    "arguments": {
      "title": "New drill press",
      "amount": 249.99,
      "created_by": 1,
      "description": "Upgrade for metal workshop",
      "url": "https://example.com/drill-press",
      "image": {
        "data": "iVBORw0KGgoAAA...",
        "mime_type": "image/png"
      },
      "basic_supplies": false
    }
  }
}
```

## Proposal read compatibility guarantees

`list_proposals` retains JSON-RPC transport authentication/error envelopes and a tool
payload containing page `count`, `limit`, `offset`, and `proposals`. Shared identifiers,
vote aggregates, and the basic-supplies flag are integers; amounts are numeric. Creator
`username`, lifecycle dates (`processed_at`, `over_budget_at`, `purchased_at`),
`image_filename`, `votes`, and `comments` remain available. Lifecycle/image fields may
be null; votes/comments are arrays with member identity and creation timestamps. Original
`url` remains separate from configured public `proposal_url` and `image_url`; unavailable
public links are null. Keep status/age, exact proposal-ID/creator filtering, ordering,
and pagination checks. REST's `success` field and smaller row shape are intentionally
separate; no new matching `total` is implied.

## Deadline warnings

`create_proposal` accepts optional `voting_deadline`; `create_poll` accepts optional
`closes_at`. Both require future ISO datetimes including timezone, or null for none.
They are normalized to UTC-naive ISO strings in storage and exposed in read results.
All three copy tools accept optional `deadline`: future timezone-qualified datetime
for proposals/polls, current/future YYYY-MM-DD for group purchases. Old deadlines
are always cleared unless an override is supplied.

The platform checks once per minute for still-open voting/joining periods entering
the final 24 hours and posts one warning per item/deadline to the configured Telegram
group/thread. It catches up within that window after downtime and skips expired,
closed, deleted or changed deadlines. Group-purchase dates end at the following local
midnight in the configured platform timezone (Europe/Madrid by default), accounting
for DST. Member-count and amount caps may close joining earlier without a predictable
24-hour warning. Records without deadlines receive no warning.

Notification claims are durable across restarts/workers. Missing Telegram configuration
leaves delivery pending. An attempted send with an ambiguous failure is recorded as
failed and not automatically replayed, avoiding duplicate announcements; creation and
copy success are not undone. See [operations](../OPERATIONS.md#platform-notifications).
