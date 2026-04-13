# REST API Documentation

All API endpoints require `X-Admin-Key` header with the `ADMIN_API_KEY` value.

## Register Member

**Endpoint:** `POST /api/register`

```bash
curl -X POST http://localhost:5000/api/register \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"username": "member1", "password": "secret123", "is_admin": false}'
```

**Request Body:**
```json
{
  "username": "newmember",
  "password": "securepassword",
  "is_admin": false
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "User newmember created",
  "member_id": 5
}
```

## Create Proposal

**Endpoint:** `POST /api/proposals`

```bash
curl -X POST http://localhost:5000/api/proposals \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "LED Strips",
    "description": "RGB LED strips for workshop",
    "amount": 75.50,
    "url": "https://example.com/led",
    "basic_supplies": false,
    "created_by": 1
  }'
```

**Request Body:**
```json
{
  "title": "LED Strips",
  "description": "RGB LED strips for workshop",
  "amount": 75.50,
  "url": "https://example.com/led",
  "basic_supplies": false,
  "created_by": 1
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "Proposal created",
  "proposal_id": 12
}
```

## Edit Proposal

**Endpoint:** `PUT /api/proposals/<id>`

```bash
curl -X PUT http://localhost:5000/api/proposals/12 \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated Title", "amount": 100}'
```

**Request Body:** (all fields optional)
```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "amount": 100,
  "url": "https://example.com/new-link",
  "basic_supplies": true
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Proposal updated",
  "proposal_id": 12
}
```

## API Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request |
| 401 | Unauthorized |
| 404 | Not found |
| 409 | Conflict (e.g., username exists) |
| 503 | API not configured |
