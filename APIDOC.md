# REST API Documentation

This project exposes a small admin-focused REST API.

## Authentication

All endpoints require:
- Header: `X-Admin-Key: <ADMIN_API_KEY>`
- `ADMIN_API_KEY` must be configured in environment.
- `Content-Type: application/json` for all request bodies.

If API key is missing in server config: `503 {"error": "API not configured"}`.
If header key is wrong/missing: `401 {"error": "Unauthorized"}`.

## Behavior notes
- API routes are authenticated by `X-Admin-Key` and are CSRF-exempt by design.
- If `Content-Type` is not JSON, endpoints return `415`.
- If JSON is missing/invalid, endpoints return `400`.

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
curl -X POST http://localhost:5000/api/register \
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
- `created_by` required and must exist in `members`
- `description`, `url`, `basic_supplies` optional

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
- `400` invalid payload / missing required fields / non-positive amount
- `404` creator member not found
- `500` unexpected DB/runtime error

### Notes
- API proposal creation does **not** auto-vote.
- If `basic_supplies = true` and `amount > 20`, basic flag is auto-removed and a comment is inserted.

### Example
```bash
curl -X POST http://localhost:5000/api/proposals \
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
curl http://localhost:5000/api/proposals/12 \
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
curl -X PATCH http://localhost:5000/api/proposals/12 \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title":"Updated Title","amount":100}'
```

---


## 5) List Proposals

**Endpoint**: `GET /api/proposals`

### Query params
- `status` (optional): one of `active`, `accepted`, `rejected`, `purchased`
- `limit` (optional): default `50`, max `200`
- `offset` (optional): default `0`

### Success response
**200 OK**
```json
{
  "success": true,
  "count": 2,
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

### Error responses
- `400` invalid `status` filter

---

## 6) List Polls

**Endpoint**: `GET /api/polls`

### Request headers
- `X-Admin-Key: <ADMIN_API_KEY>`

### Success response
**200 OK**
```json
{
  "success": true,
  "polls": [
    {
      "id": 3,
      "question": "Where should we meet?",
      "status": "open",
      "created_at": "2026-05-03 18:20:00",
      "created_by": 1,
      "total_votes": 4,
      "options": ["Room A", "Room B"]
    }
  ]
}
```

### Example
```bash
curl http://localhost:5000/api/polls \
  -H "X-Admin-Key: your_api_key"
```

### Error responses
- `401` unauthorized (missing or wrong `X-Admin-Key`)
- `503` API not configured (`ADMIN_API_KEY` missing)

---

## 6) Create Poll

**Endpoint**: `POST /api/polls`

### Request headers
- `Content-Type: application/json`
- `X-Admin-Key: <ADMIN_API_KEY>`

### Request body
```json
{
  "question": "Where should we meet?",
  "options": ["Room A", "Room B"],
  "created_by": 1
}
```

### Validation
- `question` required, 5..200 chars
- `options` required, array with 2..12 non-empty entries, max 120 chars each
- `created_by` required and must exist in `members`

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
- `400` invalid payload / validation failure
- `404` creator member not found

### Example
```bash
curl -X POST http://localhost:5000/api/polls \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"question":"Where should we meet?","options":["Room A","Room B"],"created_by":1}'
```

---


## 7) List Member Telegram Links

**Endpoint**: `GET /api/members/telegram`

### Query params
- `include_unlinked` (optional, default `false`): when true, include all members and add `linked` field (`1`/`0`).
- `limit` (optional): default `100`, max `500`
- `offset` (optional): default `0`

### Success response
**200 OK**
```json
{
  "success": true,
  "count": 1,
  "members": [
    {
      "id": 1,
      "username": "alice",
      "telegram_username": "alice_tg",
      "telegram_user_id": 123456,
      "linked": 1
    }
  ]
}
```

### Example
```bash
curl "http://localhost:5000/api/members/telegram?include_unlinked=true"   -H "X-Admin-Key: your_api_key"
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

## Related UI budget chart note (non-API)

Although not part of the REST API surface, the `/calendar` page renders a mixed Chart.js line/bar chart where:
- `pending` accumulates from proposals when they go over_budget (tracked by `over_budget_at`).
- `pending` decreases when over_budget proposals get approved.
- `Committed = cash_balance - pending`.
- Positive committed values indicate remaining budget after pending commitments.
- Negative committed values indicate budget debt (pending commitments exceed cash).
- `Budget Balance` and `Committed` lines are configured with different stack keys to prevent line-on-line visual stacking.


---

## MCP Server

The project also exposes an MCP JSON-RPC server (`app/mcp_server.py`) for admin tooling.

### Authentication
- Configure `MCP_API_KEY` in environment.
- Every MCP request (except `notifications/initialized`) must include:
  - `params.api_key: <MCP_API_KEY>`

If key is missing/invalid, server responds with JSON-RPC error code `-32001` and message:
`Unauthorized: invalid or missing MCP api_key`.

### Run modes
1. **Standalone stdio**
```bash
python -m app.mcp_server
```

2. **Alongside Flask app (TCP)**
Set environment variables:
- `MCP_SERVER_ENABLED=true`
- `MCP_SERVER_HOST` (optional, default `127.0.0.1`)
- `MCP_SERVER_PORT` (optional, default `8765`)

Then start app normally (`python app.py`).

### Implemented MCP tools
- `list_proposals`
  - optional args: `status` (`active|accepted|rejected|purchased`), `limit` (1..200), `offset` (>=0)
- `current_budget`
- `list_member_telegram_links` (optional `include_unlinked`, `limit`, `offset`)

### Example MCP request
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
