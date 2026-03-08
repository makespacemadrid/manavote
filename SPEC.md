# Hackerspace Budget Voting System - Specification

## Project Overview
- **Project name**: Hackerspace Budget Voting
- **Type**: Flask web application
- **Core functionality**: Voting system for 50 members to approve/disapprove spending proposals, with automatic Telegram notifications for approved proposals
- **Target users**: Hackerspace members (~50 people)

## Budget Rules
- Starting budget: 300 EUR
- Monthly addition: 50 EUR (on 1st of each month)
- Minimum approval threshold: 10% of members (5 members for 50 members)
- Proposals must be fully covered by current budget to be approved

## Functionality Specification

### Core Features
1. **Member Management**
   - Simple authentication (username/password stored as hashed)
   - Admin can add/remove members
   - ~50 member capacity

2. **Proposal System**
   - Create proposal with: title, description, amount (EUR)
   - Members vote: Approve or Reject
   - One vote per member per proposal
   - Vote can be changed until proposal is processed

3. **Approval Logic**
   - Check if net votes (favor - against) >= 10%+ threshold (minimum 5 for 50 members)
   - Check if budget can cover the proposal
   - If both conditions met: approve, deduct from budget, notify Telegram
   - If not approved: mark as rejected/expired

4. **Budget Tracking**
   - Display current available budget
   - Show transaction history (approved proposals)
   - Monthly automatic top-up

5. **Telegram Integration**
   - Bot token configuration
   - Chat ID for the hackerspace group
   - Send message when proposal is approved

### User Interface
- Login page
- Dashboard with current budget and proposal list
- Create proposal form
- Proposal detail page with voting
- Admin page for member management

## Technical Implementation

### Data Storage
- SQLite database (simple, no external deps)
- Tables: members, proposals, votes

### Routes
- `/` - Login or dashboard (if authenticated)
- `/login` - Login page
- `/logout` - Logout
- `/dashboard` - Main dashboard
- `/proposal/new` - Create new proposal
- `/proposal/<id>` - View and vote on proposal
- `/admin` - Member management (admin only)

## Acceptance Criteria
1. Members can log in and vote
2. Proposals with 10%+ approval votes that fit budget are automatically approved
3. Approved proposals trigger Telegram notification
4. Budget correctly tracks spending and monthly additions
5. Vote count is visible on each proposal
6. Admins can manage members
