# Hackerspace Budget Voting System

A Flask web application for managing and voting on budget proposals in a hackerspace community.

## Features

- **Member Authentication**: Simple username/password login
- **Self-Registration**: Members can register themselves (admin can disable)
- **Password Change**: Members can change their own password
- **Admin Registration via API**: Register members programmatically
- **Proposal System**: Create proposals with title, description, amount, URL, and image
- **Edit Proposals**: Creators and admins can edit active proposals
- **Delete Proposals**: Creators and admins can delete active proposals
- **Comments**: Members can comment on proposals
- **Admin Comment Management**: Admins can edit/delete any comment
- **Voting**: Members vote Approve or Reject (one vote per member, changeable)
- **Automatic Approval**: Proposals auto-approve when thresholds met and budget available
- **Pending Budget Queue**: Proposals waiting for budget auto-approve when funds available
- **Budget Tracking**: Real-time budget display calculated from transaction history
- **Admin Budget Control**: Manually add budget with description
- **Configurable Thresholds**: Admin can adjust approval thresholds
- **Telegram Notifications**: Auto-notify on new proposals and approvals
- **Purchase Tracking**: Mark approved proposals as purchased
- **Proposal Tags**: Visual tags for basic, standard (≤€50), expensive (>€50), and purchased
- **Dashboard Filters**: Filter proposals by status, purchase state, and category (Basic, Standard, Expensive)
- **REST API**: Programmatic member and proposal management

## Budget Rules

- **Starting budget**: 300 EUR
- **Monthly addition**: Configurable (default 50 EUR)
- **Approval thresholds** (net votes = favorable - against):
  - Basic supplies: 5% (selectable when creating proposal)
  - Expensive (>€50): 20%
  - Other proposals: 10%
- Proposals must fit within budget to be approved
- Proposals meeting threshold but over budget auto-approve when funds available

## Proposal Tags

| Tag | Condition | Color |
|-----|-----------|-------|
| basic | basic_supplies flag set | Yellow |
| standard | approved, ≤€50, not basic | Cyan |
| expensive | approved, amount > €50 | Purple |
| purchased | marked as purchased | Green |
| pending budget | over_budget status | Orange |

## Dashboard Filters

| Filter | Query |
|--------|-------|
| All | All proposals |
| Active | status = 'active' |
| Approved | status = 'approved' |
| Pending Budget | status = 'over_budget' |
| Purchased | purchased_at IS NOT NULL |
| Pending Purchase | status = 'approved' AND purchased_at IS NULL |
| Basic | basic_supplies = 1 |
| Standard | approved, ≤€50, not basic |
| Expensive | approved, >€50 |

## Setup

### Docker (Recommended)

```bash
docker-compose up --build
```

### Manual

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp sample.env .env
# Edit .env with your settings
```

3. Run:
```bash
python app.py
```

4. Access at http://localhost:5000

## Default Admin

- Username: `admin`
- Password: `carpediem42`

**Important**: Change this password immediately and configure `ADMIN_API_KEY` for API access.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID for notifications |
| `ADMIN_API_KEY` | Yes (for API) | Secret key for REST API authentication |

## REST API

All API endpoints require `X-Admin-Key` header with the `ADMIN_API_KEY` value.

### Register Member

```bash
curl -X POST http://localhost:5000/api/register \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"username": "member1", "password": "secret123", "is_admin": false}'
```

### Create Proposal

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

### Edit Proposal

```bash
curl -X PUT http://localhost:5000/api/proposals/12 \
  -H "X-Admin-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated Title", "amount": 100}'
```

### API Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request |
| 401 | Unauthorized |
| 404 | Not found |
| 409 | Conflict (e.g., username exists) |
| 503 | API not configured |

## Testing

```bash
pytest -q
```

## Tech Stack

- Flask 3.0.0
- SQLite
- Telegram Bot API
- Docker
- Pytest

## File Structure

```
├── app.py              # Main application
├── static/uploads/     # Image uploads
├── templates/          # HTML templates
├── tests/              # Test suite
├── requirements.txt    # Dependencies
└── docker-compose.yml  # Docker config
```

## Screenshots

The system includes:
- Login/registration pages
- Dashboard with budget and proposals
- Proposal detail with voting and comments
- Admin panel for member and budget management