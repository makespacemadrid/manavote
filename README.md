# Hackerspace Budget Voting System

A Flask + SQLite application for managing budget proposals in a hackerspace.

![Proposals](/static/img/proposals.png)
![Budget](/static/img/calendar.png)

## What it does

- Members can create, discuss, and vote on proposals.
- Members can monitor progress from the Proposals and Budget views.
- Proposals are auto-processed based on vote thresholds and available budget.
- Members can participate in transparent polls in web and Telegram.
- Admins can manage members, thresholds, settings, and budget movements.
- UI supports English and Spanish.

## Core features

- **Proposals**: weighted vote thresholds, creator auto-vote, edit/delete by owner/admin, approval undo, purchase tracking.
- **Polls**: 2..12 options, transparent results, close/reopen/delete, web/Telegram vote modes.
- **Group purchases**: shared orders with individually priced options, proportional shipping/tax costs, per-member quantities, deadlines, payment tracking, fulfillment states, and Telegram lifecycle notifications.
- **Telegram integration**: `/link`, `/vote`, `/pvote`, inline callbacks, and an optional Ocabra-compatible natural-language assistant with MCP tools, DB-backed access, confirmed admin mutations, retry deduplication, and bounded background work.
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
- Startup health, reason codes, and production diagnostics: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- Architecture diagrams (process, request/webhook flows, confirm state machine, data model): [`docs/DIAGRAMS.md`](docs/DIAGRAMS.md)

## Documentation

- Main docs index: [`docs/INDEX.md`](docs/INDEX.md)
- Direct links: [`docs/QUICKSTART.md`](docs/QUICKSTART.md), [`docs/APIDOC.md`](docs/APIDOC.md), [`docs/SPEC.md`](docs/SPEC.md), [`docs/OPERATIONS.md`](docs/OPERATIONS.md), [`docs/TESTING.md`](docs/TESTING.md), [`docs/DIAGRAMS.md`](docs/DIAGRAMS.md)

## Acknowledgements

The natural-language Telegram assistant was inspired by Luis Rivera's
[`ocabra_telegram`](https://github.com/luisriverag/ocabra_telegram) project. ManaVote
adapts its OpenAI-compatible Telegram conversation approach to the existing webhook,
database-backed member access controls, and MCP tools in this application.

## Frontend development

The shared application shell is implemented in React and built with Vite, while Flask
continues to provide routing, authentication, and server-rendered page content during
the incremental migration.

```bash
npm install
npm run dev      # continuously rebuilds assets while Flask is running
npm run build    # writes production assets to static/react
npm test
```

The production Docker image builds the React bundle automatically.
