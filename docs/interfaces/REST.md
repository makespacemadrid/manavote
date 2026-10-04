# REST API Reference

This document owns ManaVote's HTTP API contract: authentication, request and response
payloads, status codes, rate limits, and error semantics. For product rules, see
[`../SPEC.md`](../SPEC.md); for MCP or Telegram, return to the
[interface index](../APIDOC.md).

## Contents

- [Authentication and shared behavior](#rest-authentication)
- [Member feedback](#member-feedback)
- [Register member](#1-register-member)
- [Create proposal](#2-create-proposal)
- [Get proposal](#3-get-proposal)
- [Edit proposal](#4-edit-proposal)
- [List proposals](#5-list-proposals)
- [List polls](#6-list-polls)
- [Create poll](#7-create-poll)
- [List member Telegram links](#8-list-member-telegram-links)
- [Common status codes](#common-status-codes)
- [User statistics](#user-statistics-api)
- [Voting settings](#voting-settings-api)

## REST authentication

Except for member feedback, REST endpoints require:

- Header: `X-Admin-Key: <ADMIN_API_KEY>`
- `ADMIN_API_KEY` configured in the environment
- `Content-Type: application/json` for requests with bodies

If the API key is missing from server configuration, the API returns
`503 {"error": {"code": "not_configured", "message": "API not configured"}}`. If the
header key is wrong or missing, it returns
`401 {"error": {"code": "unauthorized", "message": "Unauthorized"}}`.

Every REST error response uses the same nested envelope: `error.code` is a stable,
machine-readable string and `error.message` is human-readable. REST errors never use a
bare top-level `error` string.

## REST behavior

- Admin API routes use `X-Admin-Key` and are CSRF-exempt by design.
- A request body with a non-JSON content type returns `415`.
- A missing or invalid JSON body returns `400`.
- All `/api/*` routes share a default limit of 200 requests/day and 100/hour per client;
  `POST /api/register` additionally allows 10 requests/minute. Exceeding a limit returns
  `429`.

## Member feedback

Feedback is the exception to admin-key REST authentication: it uses the
logged-in web session. `POST /api/feedback` accepts
`{"category":"bug|suggestion|other","message":"..."}` from any member. Administrators
can use `GET /api/feedback?status=&category=&limit=&offset=` and
`PATCH /api/feedback/<id>` with `{"status":"new|reviewed|resolved"}` to triage it.
Validation failures use the standard error envelope; stable codes include
`invalid_category`, `message_required`, `message_too_long`, `invalid_status`, and
`feedback_not_found`.

---

## 1) Register Member

**Endpoint**: `POST /api/register`

### Request headers
- `Content-Type: application/json`
- `X-Admin-Key: <ADMIN_API_KEY>`

### Request body
```json
{
  "username": "newmember",
  "password": "securepassword",
  "is_admin": false
}
```

### Validation
- `username` required
- `password` required
- `is_admin` optional (defaults to `false`)

### Success response
**201 Created**
```json
{
  "success": true,
  "message": "User newmember created",
  "member_id": 5
}
```

### Error responses
- `415` content type is not `application/json`
- `400` JSON body missing / required fields missing
- `409` username already exists
- `500` unexpected DB/runtime error

### Example
```bash
curl -X POST http://localhost:45000/api/register \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"username":"member1","password":"secret123","is_admin":false}'
```

---

## 2) Create Proposal

**Endpoint**: `POST /api/proposals`

### Request headers
- `Content-Type: application/json`
- `X-Admin-Key: <ADMIN_API_KEY>`

### Request body
```json
{
  "title": "LED Strips",
  "description": "RGB LED strips for workshop",
  "amount": 75.5,
  "url": "https://example.com/led",
  "basic_supplies": false,
  "created_by": 1
}
```

### Validation
- `title` required
- `amount` required, numeric, and must be `> 0`
- `created_by` required and must exist in `members`; a non-positive or otherwise
  unmatched value is rejected as `creator_member_not_found`, not a params-shape error
- `description`, `url`, `basic_supplies` optional; `basic_supplies` must parse as a
  boolean (`true`/`false`, `1`/`0`, or the equivalent string forms) when provided

### Success response
**201 Created**
```json
{
  "success": true,
  "message": "Proposal created",
  "proposal_id": 12
}
```

### Error responses
- `415` content type is not `application/json`
- `400` `title_amount_required`, `amount_must_be_positive`, `created_by_required`, or `invalid_basic_supplies`
- `404` `creator_member_not_found`
- `500` `proposal_create_failed`

### Notes
- API proposal creation does **not** auto-vote.
- If `basic_supplies = true` and `amount > 20`, basic flag is auto-removed and a comment is inserted.

### Example
```bash
curl -X POST http://localhost:45000/api/proposals \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"LED Strips",
    "description":"RGB LED strips for workshop",
    "amount":75.5,
    "url":"https://example.com/led",
    "basic_supplies":false,
    "created_by":1
  }'
```

---

## 3) Get Proposal

**Endpoint**: `GET /api/proposals/<proposal_id>`

### Request headers
- `X-Admin-Key: <ADMIN_API_KEY>`

### Success response
**200 OK**
```json
{
  "success": true,
  "proposal": {
    "id": 12,
    "title": "LED Strips",
    "description": "RGB LED strips for workshop",
    "amount": 75.5,
    "url": "https://example.com/led",
    "created_by": 1,
    "status": "active",
    "created_at": "2026-05-01 10:00:00",
    "basic_supplies": 0
  }
}
```

### Error responses
- `404` proposal not found

### Example
```bash
curl http://localhost:45000/api/proposals/12 \
  -H "X-Admin-Key: your_api_key"
```

---

## 4) Edit Proposal

**Endpoint**: `PUT /api/proposals/<proposal_id>` or `PATCH /api/proposals/<proposal_id>`

### Request headers
- `Content-Type: application/json`
- `X-Admin-Key: <ADMIN_API_KEY>`

### Request body (all fields optional)
```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "amount": 100,
  "url": "https://example.com/new-link",
  "basic_supplies": true
}
```

### Validation
- Proposal must exist
- Proposal must be in `active` status
- If `amount` provided, it must be numeric and `> 0`

### Success response
**200 OK**
```json
{
  "success": true,
  "message": "Proposal updated",
  "proposal_id": 12
}
```

### Error responses
- `415` content type is not `application/json`
- `400` invalid payload, missing JSON body, non-positive amount, or editing non-active proposal
- `404` proposal not found
- `500` unexpected DB/runtime error

### Example
```bash
curl -X PATCH http://localhost:45000/api/proposals/12 \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title":"Updated Title","amount":100}'
```

---


## 5) List Proposals

**Endpoint**: `GET /api/proposals`

### Query params
- `status` (optional): one of `active`, `approved`, `over_budget`, `rejected`
- `age` (optional): `recent` selects active proposals newer than 30 days; `old` selects active proposals at least 30 days old. It may only be combined with `status=active`.
- `limit` (optional): default `50`, max `200`
- `offset` (optional): default `0`

### Success response
**200 OK**
```json
{
  "success": true,
  "count": 2,
  "limit": 100,
  "offset": 0,
  "proposals": [
    {
      "id": 12,
      "title": "LED Strips",
      "amount": 75.5,
      "status": "active",
      "yes_votes": 3,
      "no_votes": 1
    }
  ]
}
```

`yes_votes` counts stored `in_favor` votes and `no_votes` counts stored `against`
votes; the response names are retained for API compatibility.

### Error responses
- `400` invalid `status`/`age` filter or `age` combined with a non-active status

---

## 6) List Polls

**Endpoint**: `GET /api/polls`

### Request headers
- `X-Admin-Key: <ADMIN_API_KEY>`

### Query params
- `limit` (optional): default `100`, max `200`
- `offset` (optional): default `0`

### Success response
**200 OK**
```json
{
  "success": true,
  "count": 1,
  "limit": 100,
  "offset": 0,
  "polls": [
    {
      "id": 3,
      "question": "Where should we meet?",
      "status": "open",
      "created_at": "2026-05-03 18:20:00",
      "created_by": 1,
      "allow_multiple": false,
      "total_votes": 4,
      "options": ["Room A", "Room B"]
    }
  ]
}
```

### Example
```bash
curl http://localhost:45000/api/polls \
  -H "X-Admin-Key: your_api_key"
```

### Error responses
- `400` invalid `limit`/`offset` (`invalid_limit`, `invalid_offset`, `limit_out_of_range`, `offset_out_of_range`)
- `401` unauthorized (missing or wrong `X-Admin-Key`)
- `503` API not configured (`ADMIN_API_KEY` missing)

---

## 7) Create Poll

**Endpoint**: `POST /api/polls`

### Request headers
- `Content-Type: application/json`
- `X-Admin-Key: <ADMIN_API_KEY>`

### Request body
```json
{
  "question": "Where should we meet?",
  "options": ["Room A", "Room B"],
  "created_by": 1,
  "allow_multiple": false
}
```

### Validation
- `question` required, 5..200 chars
- `options` required, array with 2..12 non-empty entries, max 120 chars each
- `created_by` required and must exist in `members`
- `allow_multiple` optional boolean, defaults to `false`; fixed for the poll's lifetime once created (see SPEC.md's "Multi-select polls")

### Success response
**201 Created**
```json
{
  "success": true,
  "message": "Poll created",
  "poll_id": 3
}
```

### Error responses
- `401` unauthorized (missing or wrong `X-Admin-Key`)
- `503` API not configured (`ADMIN_API_KEY` missing)
- `415` content type is not `application/json`
- `400` `invalid_poll_question`, `invalid_poll_options`, `invalid_allow_multiple`, or `created_by_required`
- `404` `creator_member_not_found`
- `500` `poll_create_failed`

### Example
```bash
curl -X POST http://localhost:45000/api/polls \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"question":"Where should we meet?","options":["Room A","Room B"],"created_by":1}'
```

---


## 8) List Member Telegram Links

**Endpoint**: `GET /api/members/telegram`

### Query params
- `include_unlinked` (optional, default `false`): when true, include all members and add `linked` (`1`/`0`) plus `link_state`.
- `limit` (optional): default `100`, max `500`
- `offset` (optional): default `0`

`link_state` values:
- `linked` — `telegram_user_id` is present. A public Telegram username is optional in
  Telegram, so its absence does not change this state.
- `missing_user_id` — `telegram_username` is set but `telegram_user_id` is missing
- `unlinked` — neither Telegram identity field is set

When `include_unlinked=false` (default), only fully linked members are returned and `link_state` is always `linked`.

Every row also includes `last_linked_at` and `last_unlinked_at` (nullable timestamps) for
operator diagnostics — the last time `telegram_user_id` was established/changed (via
`/link` or an OIDC login carrying a Telegram identity) and the last time it was cleared
(admin or member self-service unlink), respectively.

### Success response
**200 OK**
```json
{
  "success": true,
  "count": 1,
  "limit": 100,
  "offset": 0,
  "members": [
    {
      "id": 1,
      "username": "alice",
      "telegram_username": "alice_tg",
      "telegram_user_id": 123456,
      "last_linked_at": "2026-08-27T10:15:00",
      "last_unlinked_at": null,
      "linked": 1,
      "link_state": "linked"
    }
  ]
}
```

### Example
```bash
curl "http://localhost:45000/api/members/telegram?include_unlinked=true"   -H "X-Admin-Key: your_api_key"
```

---


## Common status codes

| Code | Meaning |
|---:|---|
| 200 | OK |
| 201 | Created |
| 400 | Bad request |
| 401 | Unauthorized (bad/missing key) |
| 404 | Not found |
| 409 | Conflict |
| 415 | Unsupported media type |
| 500 | Server error |
| 503 | API not configured |

---

## User statistics API

**Endpoint**: `GET /api/members/statistics`

Returns lifetime participation, proposal-budget, poll, group-purchase, koin-usage, and
beverage-consumption statistics.
Results support `limit` (default `100`, maximum `500`) and `offset` (default `0`).
`count` is the number of users in the current page; `total` is the number of matching
members before pagination. Email addresses are omitted unless the administrator passes
`include_email=true`.

```bash
curl "http://localhost:45000/api/members/statistics?limit=100&offset=0" \
  -H "X-Admin-Key: your_api_key"
```

The stable identity fields are `id`, `username`, and `is_admin`; `email` is present only
when explicitly requested. Count and amount fields are non-null and use `0` when no
matching activity exists. Amount fields are expressed in euros and percentage/average
fields are rounded to two decimal places.

| Area | Fields |
|---|---|
| Proposal participation | `proposal_vote_count`, `proposal_count`, `approved_proposal_count`, `comment_count` |
| Proposal budgets | `proposed_budget`, `approved_proposal_budget`, `approved_budget_percentage` |
| Polls | `poll_vote_count`, `poll_count`, `open_poll_count`, `closed_poll_count`, `created_poll_vote_count`, `average_votes_per_created_poll` |
| Group purchases | `group_purchase_count`, `open_group_purchase_count`, `created_group_purchase_order_value`, `created_group_purchase_participant_count` |
| Koins | `coin_balance`, `coins_earned`, `coins_spent` |
| Beverages | `beverages_consumed`, `beverages_replenished`, `beverage_consumption` (per-item `item_id`, `item_name`, `consumed`, and `replenished`) |

```json
{
  "success": true,
  "count": 1,
  "total": 24,
  "limit": 100,
  "offset": 0,
  "users": [
    {
      "id": 7,
      "username": "member1",
      "is_admin": 0,
      "proposal_vote_count": 12,
      "proposal_count": 3,
      "approved_proposal_count": 2,
      "comment_count": 5,
      "poll_vote_count": 4,
      "poll_count": 1,
      "coin_balance": -3,
      "coins_earned": 12,
      "coins_spent": 15,
      "beverages_consumed": 15,
      "beverages_replenished": 12,
      "beverage_consumption": [
        {"item_id": 1, "item_name": "Coke", "consumed": 10, "replenished": 12},
        {"item_id": 2, "item_name": "Coke Zero", "consumed": 5, "replenished": 0}
      ]
    }
  ]
}
```

Invalid pagination or boolean values return a standard API error with HTTP `400`.

---


## Voting settings API

- `GET /api/settings/voting` — returns current voting policy settings:
  - `poll_vote_mode`
  - `proposal_vote_mode`
  - `telegram_require_linked_vote`
- `PUT|PATCH /api/settings/voting` — updates one or more settings.
  - Allowed `poll_vote_mode` / `proposal_vote_mode`: `both`, `web_only`, `telegram_only`
  - Allowed `telegram_require_linked_vote`: boolean (`true`/`false`)
