# Hackerspace Budget Voting System

A Flask web application for managing and voting on budget proposals in a hackerspace community.

## Features
- **Multi-language**: English and Spanish (switchable from Settings)
- **Self-Registration**: Members can register themselves (admin can disable)
- **Password Change**: Members can change their own password
- **REST API Registration**: Admins can register members programmatically
- **30-day persistent sessions**: Login cookies last 30 days

## Proposals
- Create proposals with title, description, amount, URL, and image
- Edit/delete active proposals (creator or admin)
- Auto-vote in_favor when creating a proposal
- Visual tags: **basic** (supplies), **standard** (≤€50), **expensive** (>€50), **purchased**

## Voting
- Members vote: **In Favor** or **Against**
- One vote per member per proposal (changeable)
- Withdraw vote on active proposals
- Automatic approval when thresholds met and budget available
- Pending budget queue for proposals waiting for funds

## Dashboard
- Real-time budget from transaction history
- Filter by: All, Active, Approved, Pending Budget, Purchased, Pending Purchase
- Filter by category: Basic, Standard, Expensive

## Calendar
- Activity timeline: proposal submissions, approvals, rejections
- Budget graph showing cash flow and commitments over time
- Colored category legend

## Budget Chart
The calendar shows a budget graph with:
- **Budget Balance** (cyan line): Running cash balance from transactions
- **Committed** (orange line): Available budget after reserving over_budget items
- **Approved** (red bar): Budget committed when items approved (reduces available budget)
- **Cash In** (green bar): Money received (mercadillo sales, monthly top-up)
- **Cash Out** (red bar): Actual cash payments for purchased items

## Budget & Admin
- Budget tracking with full transaction history
- Manual budget additions with description
- Configurable vote thresholds
- Telegram notifications on new proposals and approvals
- Mark approved proposals as purchased
- REST API for member and proposal management
- Add/remove members
- Make/remove admin users

## Settings
- Change Password: Update your password
- Logout: End session
- Language: Switch between English and Español

## Budget Rules
- **Starting budget**: 300 EUR
- **Monthly addition**: 50 EUR (configurable)
- **Thresholds**: Basic 5%, Expensive 20%, Standard 10%
- Over-budget proposals auto-approve when budget available

## Setup

### Docker (Recommended)
```bash
docker-compose up --build
```

### Manual
```bash
pip install -r requirements.txt
cp sample.env .env
python app.py
```

## Default Admin
- Username: `admin`
- Password: `carpediem42`

## REST API
See [APIDOC.md](APIDOC.md) for full API documentation.

## Tech Stack
- Flask 3.0.0, SQLite, Jinja2 templates, Docker

## Testing
```bash
python3 -m unittest discover -s tests -v
```

All tests pass (21 tests, including language switching, translations, and budget functionality).

## Translations
- Translations stored in `translations.py` (separate from `app.py` for Docker mount)
- Filter buttons use Title Case: All, Active, Approved, Pending Budget, etc.
- Status tags use lowercase: active, approved, pending_budget, etc.