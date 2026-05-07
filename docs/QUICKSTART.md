# Quick Start

### Docker
```bash
cp sample.env .env
docker compose up --build
```

### Local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp sample.env .env
python app.py
```

App runs on `http://localhost:5000`.

## Initial admin bootstrap
- Username: `admin`
- Password: set via `ADMIN_BOOTSTRAP_PASSWORD` on first startup (required in production; in non-production it falls back to an insecure default and logs a warning)

## Configuration
Environment variables are read from `.env` (see `sample.env`).

When running with Docker Compose:
- `.env` is loaded via `env_file`.
- Persistent data uses Docker named volumes:
  - `app_data` → `/data` (database at `/data/app.db`)
  - `uploads_data` → `/app/static/uploads`

| Variable | Default | Purpose |
|---|---:|---|
| `FLASK_ENV` | _empty_ | Set to `production` to enable production-safe checks |
| `SECRET_KEY` | _empty_ | Required when `FLASK_ENV=production`; used for session + CSRF signing |
| `FLASK_DEBUG` | `false` | Flask debug mode |
| `FLASK_CSRF` | `true` | Flask-WTF CSRF protection toggle (enabled by default) |
| `FLASK_SECURE_COOKIES` | `true` | Enables `SESSION_COOKIE_SECURE` (recommended default) |
| `ADMIN_BOOTSTRAP_PASSWORD` | _empty_ | Required for first-time admin creation in production; non-production falls back to insecure default with warning |
| `ADMIN_API_KEY` | _empty_ | Required for REST API endpoints |
| `MCP_API_KEY` | _empty_ | Required for MCP JSON-RPC authentication |
| `MCP_SERVER_ENABLED` | `false` | Enables in-process MCP server when set to `true` |
| `MCP_SERVER_HOST` | `127.0.0.1` | MCP bind host (`0.0.0.0` for container/network access) |
| `MCP_SERVER_PORT` | `8765` | MCP server port |
| `APP_DB_PATH` | `<repo>/app.db` | Optional SQLite path override (useful for test isolation) |
| `TELEGRAM_BOT_TOKEN` | _empty_ | Telegram integration token |
| `TELEGRAM_CHAT_ID` | _empty_ | Telegram target chat |
| `TELEGRAM_THREAD_ID` | _empty_ | Optional Telegram topic/thread id for forum chats |
| `TELEGRAM_ADMIN_ID` | _empty_ | Optional Telegram user/chat id for poll test messages from admin panel |
| `TELEGRAM_WEBHOOK_SECRET` | _empty_ | Secret path segment used by Telegram webhook endpoint for command/inline-button poll voting |

### Telegram poll delivery notes (important)
- Poll text is sent as plain text (no forced Markdown parse mode) to avoid Telegram rejecting messages with unescaped markdown-like characters.
- If users report "buttons missing", check:
  1. bot is admin in the target chat,
  2. webhook URL includes the exact `TELEGRAM_WEBHOOK_SECRET`,
  3. bot can receive callback queries in that chat/topic,
  4. app logs for failed `editMessageReplyMarkup` / `answerCallbackQuery`.

### Telegram webhook is app-managed
You do **not** need to run `/setwebhook` manually in BotFather.

1. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, and Base URL in Admin → Telegram Configuration.
2. Click **Sync Telegram Webhook** (or save Base URL; the app auto-attempts sync).
3. Ensure app is reachable via public HTTPS URL.
4. Keep bot in target chat with required permissions.

The app configures webhook URL as:
`https://<base-url>/telegram/webhook/<TELEGRAM_WEBHOOK_SECRET>`

If webhook is missing/misconfigured, poll messages may appear but inline button taps will not record votes.

### Auto-backup scheduler notes
- Auto-backup uses APScheduler (`apscheduler.schedulers.background.BackgroundScheduler`).
- If logs show APScheduler unavailable, install it in the same runtime environment used by the app:
  - `pip install APScheduler`
  - verify with: `python -c "import apscheduler; print(apscheduler.__version__)"`

Additional operational notes:
- Web forms are protected with Flask-WTF `CSRFProtect`.
- API endpoints under `/api/*` are CSRF-exempt and authenticated with `X-Admin-Key`.
- Docker image runs as a non-root user.
- Health endpoint available at `GET /healthz` (used by compose healthcheck).
- MCP endpoints available when enabled: `POST /mcp` and `GET /healthz` on `MCP_SERVER_HOST:MCP_SERVER_PORT`.
- Set `SECRET_KEY` and `ADMIN_BOOTSTRAP_PASSWORD` explicitly in production deployments (do not rely on fallback defaults).


## Backup

- Manual: Admin → Budget → "Backup Database" button
- Auto: Runs every 24 hours via APScheduler (if installed), keeps last 7 backups
- Backup files: `app.db`

## Testing
```bash
pytest -q
```

Focused regression slice for the ongoing route decomposition:

```bash
pytest -q tests/test_blueprint_registration.py tests/test_blueprint_endpoint_aliases.py tests/test_api_helpers.py tests/test_production_config.py
```
