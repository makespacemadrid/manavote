# Hackerspace Budget Voting System - Specification

## Project Overview
- **Project name**: Hackerspace Budget Voting
- **Type**: Flask web application
- **Core functionality**: Voting system for 50 members to approve/disapprove spending proposals, with automatic Telegram notifications for approved proposals
- **Target users**: Hackerspace members (~50 people)

## Budget Rules
- Starting budget: 300 EUR
- Monthly addition: 50 EUR (on 1st of each month)
- Minimum approval threshold: varies by proposal type (see below)
- Proposals must be fully covered by current budget to be approved

## Functionality Specification

### Core Features
1. **Member Management**
   - Simple authentication (username/password stored as hashed)
   - Admin can add/remove members
   - Self-registration for new members
   - ~50 member capacity

2. **Proposal System**
   - Create proposal with: title, description, amount (EUR), optional URL, optional image (JPG/PNG)
   - Edit proposals while active (creator or admin)
   - Members vote: Approve or Reject
   - One vote per member per proposal
   - Vote can be changed until proposal is processed
   - Comments on proposals

3. **Approval Logic**
   - Check if net votes (favor - against) >= threshold
   - Threshold varies by proposal type and amount:
     - Basic supplies: 5% of members (minimum 1)
     - Proposals over €50: 20% of members
     - Other proposals: 10% of members
   - Check if budget can cover the proposal
   - If both conditions met: approve, deduct from budget, notify Telegram
   - If votes meet threshold but budget insufficient: mark as "over_budget" (auto-approves when budget becomes available)
   - If votes don't meet threshold: remains active for more voting

4. **Budget Tracking**
   - Display current available budget ("Budget for New Toys")
   - Show transaction history (approved proposals, manual additions, monthly top-ups)
   - Monthly automatic top-up
   - Admin can manually add budget with description

5. **Admin Features**
   - Manage members (add/remove)
   - Manually increase budget with description
   - Edit/delete any comment
   - Undo proposal approvals
   - Trigger monthly top-up manually

6. **Telegram Integration**
   - Bot token configuration
   - Chat ID for the hackerspace group
   - Send message when proposal is approved

### User Interface
- Login page
- Registration page
- Dashboard with current budget and proposal list
- Create proposal form
- Proposal detail page with voting and comments
- Admin page for member and budget management

## Technical Implementation

### Data Storage
- SQLite database (simple, no external deps)
- Tables: members, proposals, votes, comments, settings, budget_log

### Routes
- `/` - Login or dashboard (if authenticated)
- `/login` - Login page
- `/register` - Registration page
- `/logout` - Logout
- `/dashboard` - Main dashboard
- `/proposal/new` - Create new proposal
- `/proposal/<id>` - View and vote on proposal
- `/proposal/<id>/edit` - Edit proposal
- `/comment/<id>/edit` - Edit comment (admin)
- `/comment/<id>/delete` - Delete comment (admin)
- `/admin` - Admin panel (member and budget management)

## Acceptance Criteria
1. Members can log in and vote
2. Proposals with required net votes that fit budget are automatically approved
   - Basic supplies: 5% threshold
   - Proposals over €50: 20% threshold
   - Other proposals: 10% threshold
3. Approved proposals trigger Telegram notification
4. Budget correctly tracks spending and monthly additions
5. Vote count is visible on each proposal
6. Admins can manage members
7. Admins can edit/delete comments
8. Admins can manually add budget with description
9. Proposals that meet vote threshold but exceed budget are marked "over_budget" and auto-approve when budget becomes available
