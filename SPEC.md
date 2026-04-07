# Hackerspace Budget Voting System - Specification

## Project Overview
- **Project name**: Hackerspace Budget Voting
- **Type**: Flask web application
- **Core functionality**: Voting system for members to approve/disapprove spending proposals, with automatic Telegram notifications for approved proposals
- **Target users**: Hackerspace members (~50 people)

## Architecture
- **Framework**: Flask monolith (`app.py`) with server-rendered Jinja templates
- **Database**: SQLite (`hackerspace.db`) with direct SQL (no ORM)
- **State & auth**: Cookie-based Flask sessions (`session[member_id|username|is_admin]`)
- **Notifications**: Telegram Bot API via `requests.post`
- **File uploads**: Proposal images in `static/uploads/`

## Data Model

### `members`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| username | TEXT UNIQUE | Required |
| password_hash | TEXT | SHA-256 hex |
| is_admin | INTEGER | 0 or 1 |
| created_at | TEXT | Default CURRENT_TIMESTAMP |

### `proposals`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Required |
| description | TEXT | |
| amount | REAL | Required |
| url | TEXT | Optional |
| image_filename | TEXT | Optional, JPG/PNG |
| created_by | INTEGER | FK to members.id |
| created_at | TEXT | Default CURRENT_TIMESTAMP |
| status | TEXT | `active`, `approved`, `over_budget` |
| processed_at | TEXT | |
| basic_supplies | INTEGER | 0 or 1 |

### `votes`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| proposal_id | INTEGER | FK to proposals.id |
| member_id | INTEGER | FK to members.id |
| vote | TEXT | `in_favor` or `against` |
| created_at | TEXT | Default CURRENT_TIMESTAMP |
| | | UNIQUE(proposal_id, member_id) |

### `comments`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| proposal_id | INTEGER | FK to proposals.id |
| member_id | INTEGER | FK to members.id |
| content | TEXT | Required |
| created_at | TEXT | Default CURRENT_TIMESTAMP |

### `budget_log`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| amount | REAL | Positive or negative |
| description | TEXT | |
| created_at | TEXT | Default CURRENT_TIMESTAMP |

### `settings`
| Column | Type | Notes |
|--------|------|-------|
| key | TEXT PK | |
| value | TEXT | |

**Used keys**: `current_budget`, `monthly_topup`, `threshold_basic`, `threshold_over50`, `threshold_default`, `registration_enabled`

## Business Rules

### Initialization Defaults
On first run:
- Default admin: username `admin`, password `carpediem42`
- `current_budget = 300`
- `monthly_topup = 50`
- `threshold_basic = 5`
- `threshold_over50 = 20`
- `threshold_default = 10`
- `registration_enabled = true`

### Voting Threshold Formula
```
min_backers = max(1, int(member_count * threshold%))
```

Threshold selection:
1. `basic_supplies == 1` → `threshold_basic` (5%)
2. Else if `amount > 50` → `threshold_over50` (20%)
3. Else → `threshold_default` (10%)

### Approval Condition
Proposal is approved when BOTH:
1. `net_votes = in_favor - against >= min_backers`
2. `proposal.amount <= current_budget`

On approval:
- status → `approved`
- `processed_at` set
- Budget decremented by amount
- Budget log entry added
- Telegram notification sent

### Over-Budget Condition
If votes meet threshold but budget insufficient:
- status → `over_budget`
- `processed_at` set
- Auto-approved (FIFO by `created_at`) when budget becomes available

## Features

### Member Management
- Simple authentication (username/password)
- Self-registration (can be disabled by admin)
- Admin member management (add/remove)
- Admin member registration via REST API

### Proposal System
- Create proposal: title, description, amount, URL (optional), image (optional, JPG/PNG)
- Edit proposals while active (creator or admin)
- Delete active proposals (creator or admin)
- Members vote: Approve or Reject
- One vote per member per proposal (changeable)
- Comments on proposals

### Budget Tracking
- Display current available budget
- Transaction history
- Monthly automatic top-up (configurable)
- Admin can manually add budget

### Admin Features
- Manage members (add/remove)
- Toggle self-registration
- Manually add budget
- Edit/delete any comment
- Undo proposal approvals
- Trigger monthly top-up
- Update vote thresholds

### REST API (X-Admin-Key authentication)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/register` | Register new member |
| POST | `/api/proposals` | Create proposal |
| PUT | `/api/proposals/<id>` | Edit proposal |

### Telegram Integration
- Bot token configuration
- Chat ID for notifications
- Auto-notify on proposal approval

## Routes

### Web Routes
| Route | Methods | Auth | Description |
|-------|---------|------|-------------|
| `/` | GET | - | Redirect to login/dashboard |
| `/login` | GET/POST | - | Login page |
| `/logout` | GET | - | Logout |
| `/register` | GET/POST | - | Registration (subject to setting) |
| `/about` | GET | - | About page |
| `/dashboard` | GET | Required | Main dashboard |
| `/proposal/new` | GET/POST | Required | Create proposal |
| `/proposal/<id>` | GET/POST | Required | View, vote, comment |
| `/proposal/<id>/edit` | GET/POST | Required | Edit (owner/admin, active only) |
| `/proposal/<id>/delete` | POST | Required | Delete (owner/admin, active only) |
| `/vote/<id>` | POST | Required | Quick vote |
| `/comment/<id>/edit` | GET/POST | Admin | Edit comment |
| `/comment/<id>/delete` | POST | Admin | Delete comment |
| `/undo/<id>` | POST | Admin | Undo approval |
| `/admin` | GET/POST | Admin | Admin panel |
| `/check-overbudget` | GET | - | Trigger over-budget check |

## Known Issues & Security Findings

### High Priority
1. **Hardcoded default admin**: `admin`/`carpediem42` created automatically
2. **Weak password hashing**: SHA-256 (should use `werkzeug.security`)
3. **No CSRF protection**: All form POSTs vulnerable
4. **Debug mode enabled**: `debug=True` in entrypoint

### Medium Priority
5. No rate limiting on login/API
6. Upload validation by extension only (no MIME check)
7. Broad `except:` blocks suppress errors
8. `/check-overbudget` unauthenticated

### Correctness
- ✅ `trigger_monthly` uses `monthly_topup` setting
- ✅ No duplicate flash in `add_budget`
- Amount parsing lacks validation guards
- Connection nesting in `process_proposal()`

### Performance
- N+1 query pattern on dashboard
- Single-file monolith
- ✅ Repeated threshold logic consolidated

## Testing

Run tests with:
```bash
pytest -q
```

Current coverage:
- Threshold calculation (`calculate_min_backers`)
- Settings float parsing fallback
- Admin monthly top-up respects setting
- No duplicate flash on add budget
