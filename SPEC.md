# Hackerspace Budget Voting System - Specification

## Project Overview
- **Project name**: Hackerspace Budget Voting
- **Type**: Flask web application
- **Core functionality**: Voting system for members to approve/disapprove spending proposals, with automatic Telegram notifications for approved proposals
- **Target users**: Hackerspace members (~50 people)

## Architecture

### Technology Stack
- **Framework**: Flask 3.0.0 (Python)
- **Database**: SQLite (`hackerspace.db`)
- **Templates**: Jinja2 (server-rendered HTML)
- **Session**: Cookie-based Flask sessions
- **Notifications**: Telegram Bot API via `requests`
- **File uploads**: Local storage in `static/uploads/`

### File Structure
```
├── app.py              # Main application (monolith)
├── static/
│   └── uploads/       # Proposal image uploads
├── templates/          # Jinja2 HTML templates
├── tests/              # pytest test suite
├── hackerspace.db      # SQLite database (gitignored)
├── .env                # Environment variables (gitignored)
├── sample.env          # Environment template
├── requirements.txt    # Python dependencies
└── docker-compose.yml # Docker deployment
```

### Startup Behavior
When run directly (`python app.py`):
1. Initialize database schema
2. Check over-budget proposals for auto-approval
3. Start Flask in debug mode on `0.0.0.0:5000`

## Data Model

### `members`
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| username | TEXT | UNIQUE, NOT NULL | Login username |
| password_hash | TEXT | NOT NULL | SHA-256 hex hash |
| is_admin | INTEGER | DEFAULT 0 | Admin flag (0/1) |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP | Registration time |

### `proposals`
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| title | TEXT | NOT NULL | Proposal title |
| description | TEXT | | Detailed description |
| amount | REAL | NOT NULL | Cost in EUR |
| url | TEXT | | Link to product/info |
| image_filename | TEXT | | Uploaded image filename |
| created_by | INTEGER | FK → members.id | Creator |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP | Creation time |
| status | TEXT | DEFAULT 'active' | `active`, `approved`, `over_budget` |
| processed_at | TEXT | | Approval/over-budget time |
| purchased_at | TEXT | | Purchase timestamp |
| basic_supplies | INTEGER | DEFAULT 0 | Basic supplies flag (0/1) |

### `votes`
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| proposal_id | INTEGER | FK → proposals.id, NOT NULL | Target proposal |
| member_id | INTEGER | FK → members.id, NOT NULL | Voter |
| vote | TEXT | NOT NULL | `in_favor` or `against` |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP | Vote time |
| | | UNIQUE(proposal_id, member_id) | One vote per member per proposal |

### `comments`
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| proposal_id | INTEGER | FK → proposals.id, NOT NULL | Target proposal |
| member_id | INTEGER | FK → members.id, NOT NULL | Commenter |
| content | TEXT | NOT NULL | Comment text |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP | Post time |

### `budget_log`
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| amount | REAL | NOT NULL | Positive or negative |
| description | TEXT | | Transaction description |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP | Transaction time |

### `settings`
| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| key | TEXT | PK | Setting name |
| value | TEXT | | Setting value |

**Default settings**:
| Key | Default | Description |
|-----|---------|-------------|
| current_budget | 300 | Available budget in EUR |
| monthly_topup | 50 | Monthly addition in EUR |
| threshold_basic | 5 | Basic supplies threshold (%) |
| threshold_over50 | 20 | Over €50 threshold (%) |
| threshold_default | 10 | Default threshold (%) |
| registration_enabled | true | Self-registration toggle |

## Business Rules

### Initialization Defaults
On first run (when no admin exists):
- Creates default admin: username `admin`, password `carpediem42`
- Initializes settings to defaults above
- Adds initial budget log: `+300 ("Ventas mercadillo marzo")`

### Budget Calculation
Budget is calculated as the SUM of all `budget_log` entries, not stored separately.

### Voting Threshold Formula
```
min_backers = max(1, int(member_count × threshold%))
```

Threshold selection order:
1. `basic_supplies == 1` → `threshold_basic` (default 5%)
2. `amount > 50` → `threshold_over50` (default 20%)
3. Otherwise → `threshold_default` (default 10%)

### Proposal Lifecycle

```
[active] → (approval) → [approved]
              ↓
       (over_budget) → [over_budget] → (budget available) → [approved]
```

#### Status: `active`
- Initial state for new proposals
- Members can vote and comment
- Creator/admin can edit or delete
- Processed after each vote

#### Status: `approved`
- Meets vote threshold AND fits budget
- Budget deducted
- Telegram notification sent
- Can be marked as purchased
- Can be undone by admin (restores budget)

#### Status: `over_budget`
- Meets vote threshold but exceeds budget
- Waits in queue (FIFO by `created_at`)
- Auto-approved when budget becomes available
- Telegram notification sent on auto-approval

### Approval Condition
Both conditions must be TRUE:
1. `net_votes = in_favor - against >= min_backers`
2. `proposal.amount <= current_budget`

### On Approval
1. status → `approved`
2. `processed_at` → current timestamp
3. Budget decremented by amount
4. Budget log entry added (negative amount)
5. Telegram message sent
6. Check over-budget queue

### On Undo Approval
1. status → `active`
2. `processed_at` → NULL
3. Budget restored by amount
4. Budget log entry added (positive amount)
5. Check over-budget queue

## Features

### Authentication
- Username/password login
- Session-based authentication (Flask sessions)
- Auto-create default admin on first run
- SHA-256 password hashing
- Password change for members

### Member Management
| Action | Who | Method |
|--------|-----|--------|
| Register | Anyone | Web form (if enabled) |
| Login | Member | Web form |
| Logout | Member | Click |
| Change password | Member | Web form |
| Add member | Admin | Web form |
| Remove member | Admin | Web form |
| Toggle registration | Admin | Admin panel |
| Register via API | Admin | REST API |

### Proposal System
| Action | Who | Constraint |
|--------|-----|------------|
| Create | Member | Auth required |
| View | Member | Auth required |
| Edit | Creator/Admin | Active status only |
| Delete | Creator/Admin | Active status only |
| Vote | Member | One per member |
| Comment | Member | |
| Mark purchased | Member | Approved only |
| Unmark purchased | Member | Approved only |

### Proposal Tags
| Tag | Condition | Color |
|-----|-----------|-------|
| basic | basic_supplies = 1 | Yellow |
| expensive | approved AND amount > 50 | Purple |
| purchased | purchased_at is set | Green |
| pending budget | status = over_budget | Orange |

### Dashboard Filters
| Filter | Query |
|--------|-------|
| All | All proposals |
| Active | status = 'active' |
| Approved | status = 'approved' |
| Pending Budget | status = 'over_budget' |
| Purchased | purchased_at IS NOT NULL |
| Pending Purchase | status = 'approved' AND purchased_at IS NULL |
| Basic | basic_supplies = 1 |
| Expensive | status = 'approved' AND amount > 50 |

### Voting
- Two options: `in_favor` / `against`
- One vote per member per proposal
- Vote can be changed (INSERT OR REPLACE)
- Proposal auto-processes after each vote
- Quick vote button on dashboard

### Budget Management
| Action | Who | Description |
|--------|-----|-------------|
| View balance | Member | Dashboard display (from log sum) |
| View history | Member | Last 50 transactions |
| Add budget | Admin | Manual addition with description |
| Monthly top-up | Admin | Adds `monthly_topup` amount |
| Undo approval | Admin | Restores budget |

### Threshold Configuration
Admins can adjust via admin panel:
- `threshold_basic`: Basic supplies approval %
- `threshold_over50`: Proposals over €50 approval %
- `threshold_default`: Other proposals approval %

## REST API

All API endpoints require `X-Admin-Key` header matching `ADMIN_API_KEY` environment variable.

### Member Registration
**`POST /api/register`**

Request:
```json
{
  "username": "newmember",
  "password": "securepassword",
  "is_admin": false
}
```

Response (201):
```json
{
  "success": true,
  "message": "User newmember created",
  "member_id": 5
}
```

### Create Proposal
**`POST /api/proposals`**

Request:
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

Response (201):
```json
{
  "success": true,
  "message": "Proposal created",
  "proposal_id": 12
}
```

### Edit Proposal
**`PUT /api/proposals/<id>`**

Request (all fields optional):
```json
{
  "title": "Updated Title",
  "amount": 100
}
```

Response (200):
```json
{
  "success": true,
  "message": "Proposal updated",
  "proposal_id": 12
}
```

### Error Responses
| Status | Meaning |
|--------|---------|
| 400 | Bad request (missing fields, invalid data) |
| 401 | Unauthorized (missing/invalid API key) |
| 404 | Not found (member/proposal doesn't exist) |
| 409 | Conflict (username already exists) |
| 503 | Service unavailable (API key not configured) |

## Routes

### Public Routes
| Route | Methods | Auth | Description |
|-------|---------|------|-------------|
| `/` | GET | - | Redirect to login/dashboard |
| `/login` | GET/POST | - | Login page |
| `/register` | GET/POST | - | Registration (subject to setting) |
| `/about` | GET | - | About page |
| `/check-overbudget` | GET | - | Trigger over-budget check |

### Protected Routes (Login Required)
| Route | Methods | Description |
|-------|---------|-------------|
| `/logout` | GET | Logout |
| `/change-password` | GET/POST | Change password |
| `/dashboard` | GET | Main dashboard |
| `/proposal/new` | GET/POST | Create proposal |
| `/proposal/<id>` | GET/POST | View, vote, comment |
| `/proposal/<id>/edit` | GET/POST | Edit proposal |
| `/proposal/<id>/delete` | POST | Delete proposal |
| `/vote/<id>` | POST | Quick vote |
| `/purchase/<id>` | POST | Mark as purchased |
| `/unpurchase/<id>` | POST | Remove purchase status |
| `/undo/<id>` | POST | Undo approval |

### Admin Routes
| Route | Methods | Description |
|-------|---------|-------------|
| `/admin` | GET/POST | Admin panel |
| `/comment/<id>/edit` | GET/POST | Edit comment |
| `/comment/<id>/delete` | POST | Delete comment |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | (empty) | Telegram bot token |
| `TELEGRAM_CHAT_ID` | (empty) | Telegram chat ID for notifications |
| `ADMIN_API_KEY` | (empty) | API authentication key |

## Telegram Notifications

Messages sent on:
1. **New proposal**: New budget request posted
2. **Proposal approved**: Budget approved
3. **Over-budget auto-approval**: Budget now available, proposal approved

## Security Findings

### High Priority
1. **Hardcoded default admin**: `admin`/`carpediem42` created on init
2. **Weak password hashing**: SHA-256 (no salt, should use `werkzeug.security`)
3. **No CSRF protection**: All form POSTs vulnerable
4. **Debug mode enabled**: `debug=True` in `app.py`

### Medium Priority
5. No rate limiting on login/API endpoints
6. Upload validation by extension only (no MIME/content check)
7. Broad `except:` blocks suppress error visibility
8. `/check-overbudget` unauthenticated

## Performance Findings
- N+1 query pattern on dashboard (per-proposal vote counts)
- Single-file monolith (`app.py`)
- ✅ Repeated threshold logic consolidated

## Testing

```bash
# Run all tests
pytest -q

# Run with verbose output
pytest -v
```

### Current Test Coverage
- Threshold calculation (`calculate_min_backers`)
- Settings float parsing fallback
- Admin monthly top-up uses `monthly_topup` setting
- No duplicate flash on add budget

## Acceptance Criteria
- [x] Members can register/login and vote
- [x] Proposals auto-approve when thresholds met and budget available
- [x] Over-budget proposals auto-approve when budget available
- [x] Telegram notifications on approval
- [x] Budget tracking with history (calculated from log)
- [x] Admin can manage members and settings
- [x] Admin can edit/delete comments
- [x] Admin can add budget manually
- [x] REST API for member/proposal management
- [x] Proposals can be deleted by creator/admin
- [x] Members can change their password
- [x] Approved proposals can be marked as purchased
- [x] Dashboard filters for status and purchase state
- [x] Proposal tags: basic, expensive, purchased