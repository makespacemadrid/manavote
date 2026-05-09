# Hackerspace Budget Voting System

A Flask + SQLite application for managing budget proposals in a hackerspace.

![Proposals](/static/img/proposals.png)
![Calendar](/static/img/calendar.png)

## What it does

- Members can create, discuss, and vote on proposals.
- Members can monitor progress from Dashboard and Calendar views.
- Proposals are auto-processed based on vote thresholds and available budget.
- Members can participate in transparent polls in web and Telegram.
- Admins can manage members, thresholds, settings, and budget movements.
- UI supports English and Spanish.

## Core features

- **Proposals**: weighted vote thresholds, creator auto-vote, edit/delete by owner/admin, approval undo, purchase tracking.
- **Polls**: 2..12 options, transparent results, close/reopen/delete, web/Telegram vote modes.
- **Telegram integration**: `/link`, `/vote`, `/pvote`, inline poll/proposal callbacks, webhook processing.
- **Budget lifecycle**: approval when threshold+budget are met, over-budget queue with auto-approval later.
- **Timezone-aware UI**: all timestamps are rendered in configured timezone.

For full behavior and edge cases, see the technical specification: [`docs/SPEC.md`](docs/SPEC.md).

## Quick start

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for Docker/local setup, bootstrap, and environment variables.

## API + MCP

- REST API and request/response examples: [`docs/APIDOC.md`](docs/APIDOC.md)
- MCP server usage, auth, transport, and tool list: [`docs/APIDOC.md`](docs/APIDOC.md)

## Testing

- Full suite: `pytest -q`
- Additional targeted regression packs and what they validate: [`docs/TESTING.md`](docs/TESTING.md)

## Project structure

- App/runtime architecture and module map: [`docs/SPEC.md`](docs/SPEC.md)

## Documentation

- Main docs index: [`docs/INDEX.md`](docs/INDEX.md)
- Direct links: [`docs/QUICKSTART.md`](docs/QUICKSTART.md), [`docs/APIDOC.md`](docs/APIDOC.md), [`docs/SPEC.md`](docs/SPEC.md), [`docs/TESTING.md`](docs/TESTING.md)
