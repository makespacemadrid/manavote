# Hackerspace Budget Voting System

A Flask web application for managing and voting on budget proposals in a hackerspace community.

## Features

- **Member Authentication**: Simple username/password login for ~50 members
- **Self-Registration**: Members can register themselves
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
- **Admin Panel**: Manage members

## Budget Rules

- Starting budget: 300 EUR
- Monthly addition: 50 EUR (on 1st of each month)
- Minimum approval threshold: 10% of members (5 votes for 50 members)
- Proposals must be fully covered by current budget to be approved

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

## Tech Stack

- Flask
- SQLite
- Telegram Bot API
- Docker
