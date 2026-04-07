# Hackerspace Budget Voting System

A Flask web application for managing and voting on budget proposals in a hackerspace community.

## Features

- **Member Authentication**: Simple username/password login for ~50 members
- **Self-Registration**: Members can register themselves (can be disabled by admin)
- **Admin Registration via API**: Admins can register members programmatically via REST API
- **Proposal System**: Create budget proposals with title, description, amount, optional URL, and optional image (JPG/PNG)
- **Edit Proposals**: Proposal creators can edit their proposals while active
- **Comments**: Members can comment on proposals
- **Admin Comment Management**: Admins can edit/delete any comment
- **Voting**: Members can Approve or Reject proposals (one vote per member, changeable)
- **Automatic Approval**: Proposals with net votes >= threshold that fit within budget are auto-approved
   - Standard threshold: 10% (5 votes for 50 members)
   - Basic supplies: 5% threshold (3 votes for 50 members) - can be selected when creating a proposal
- **Budget Tracking**: Real-time budget display with transaction history
- **Admin Budget Control**: Admins can manually increase budget with description
- **Telegram Notifications**: Auto-notify hackerspace group when proposals are approved
- **Admin Panel**: Manage members and toggle registration settings

## Budget Rules

- Starting budget: 300 EUR
- Monthly addition: configurable via `settings.monthly_topup` (default 50 EUR, on 1st of each month)
- Approval thresholds (net votes = favorable - against):
  - Basic supplies: 5% of members - can be selected when creating a proposal
  - Proposals over €50: 20% of members
  - Other proposals: 10% of members
- Proposals must be fully covered by current budget to be approved
- Proposals meeting vote threshold but exceeding budget are marked "over_budget" and auto-approve when budget becomes available

## Setup

### Option 1: Docker (Recommended)

```bash
docker-compose up --build
```

### Option 2: Manual

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables (optional):
```bash
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID
```

3. Run the application:
```bash
python app.py
```

4. Access at http://localhost:5000

## Default Admin

- Username: `admin`
- Password: `carpediem42`

## REST API

### Member Registration

Admins can register new members via the REST API (requires API key):

**Endpoint:** `POST /api/register`

**Headers:**
```
X-Admin-Key: your_admin_api_key
Content-Type: application/json
```

**Request Body (JSON):**
```json
{
  "username": "newmember",
  "password": "securepassword",
  "is_admin": false
}
```

**Response (Success - 201):**
```json
{
  "success": true,
  "message": "User newmember created",
  "member_id": 5
}
```

**Response (Error - 401):**
```json
{
  "error": "Unauthorized"
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:5000/api/register \
  -H "X-Admin-Key: your_admin_api_key" \
  -H "Content-Type: application/json" \
  -d '{"username": "newmember", "password": "securepassword", "is_admin": false}'
```

**Setup:** Set `ADMIN_API_KEY` environment variable in `.env` file.

### Create Proposal

**Endpoint:** `POST /api/proposals`

**Headers:**
```
X-Admin-Key: your_admin_api_key
Content-Type: application/json
```

**Request Body (JSON):**
```json
{
  "title": "New LED Strips",
  "description": "RGB LED strips for workshop",
  "amount": 75.50,
  "url": "https://example.com/led-strips",
  "basic_supplies": false,
  "created_by": 1
}
```

**Response (Success - 201):**
```json
{
  "success": true,
  "message": "Proposal created",
  "proposal_id": 12
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:5000/api/proposals \
  -H "X-Admin-Key: your_admin_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New LED Strips", "description": "RGB LED strips", "amount": 75.50, "created_by": 1}'
```

### Edit Proposal

**Endpoint:** `PUT /api/proposals/<id>`

**Headers:**
```
X-Admin-Key: your_admin_api_key
Content-Type: application/json
```

**Request Body (JSON):** (all fields optional, only include what you want to update)
```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "amount": 100,
  "url": "https://example.com/new-link",
  "basic_supplies": true
}
```

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Proposal updated",
  "proposal_id": 12
}
```

**Example with curl:**
```bash
curl -X PUT http://localhost:5000/api/proposals/12 \
  -H "X-Admin-Key: your_admin_api_key" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "title": "Updated Title"}'
```

## Tech Stack

- Flask
- SQLite
- Telegram Bot API
- Docker
- Pytest

## Testing

Run the test suite with:

```bash
pytest -q
```
