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
npm install
npm run build
cp sample.env .env
python app.py
```

App runs on `http://localhost:45000`. For frontend development, run `npm run dev` in a second terminal; it watches the React sources and continuously rebuilds the Flask-served assets.

## Initial admin bootstrap
- Username: `admin`
- Password: set via `ADMIN_BOOTSTRAP_PASSWORD` on first startup (required in production; in non-production it falls back to an insecure default and logs a warning)

## Configuration
Environment variables are read from `.env` (see `sample.env`).

When running with Docker Compose:
- `.env` is loaded via `env_file`.
- Compose also overrides a few runtime flags in `docker-compose.yml`:
  - `APP_DB_PATH=/data/app.db`
  - `MCP_SERVER_ENABLED=true`
  - `MCP_SERVER_HOST=0.0.0.0`
  - `MCP_SERVER_PORT=8765`
- Persistent data uses Docker named volumes:
  - `app_data` → `/data` (database at `/data/app.db`)
  - `uploads_data` → `/app/static/uploads`

### Migrating an existing Docker database

Older Compose configurations mounted `./app.db` directly. Back it up before moving to
the named volume, then copy it into the new container after the volume is created:

```bash
cp app.db app.db.backup
docker compose up --no-start
docker compose cp app.db web:/data/app.db
docker compose run --rm --no-deps --user root web chown appuser:appuser /data/app.db
docker compose up
```

Skip this migration for a new installation. Do not remove the original database or
its backup until the application starts and the expected proposals and members are
visible.

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
| `TELEGRAM_MCP_URL` | `http://127.0.0.1:8765/mcp` | MCP endpoint used by the Telegram `/mcp` command |
| `TELEGRAM_MCP_ALLOWED_USER_IDS` | _empty_ | Optional comma-separated additional Telegram numeric user IDs; linked member IDs are allowed automatically |
| `TELEGRAM_MCP_ALLOW_GROUPS` | `false` | Allows MCP commands and potentially sensitive results in group chats when explicitly enabled |
| `TELEGRAM_LLM_API_KEY` | _empty_ | Enables natural-language Telegram messages through an OpenAI-compatible API |
| `TELEGRAM_LLM_MODEL` | _empty_ | Chat model used by the Telegram assistant; required with the API key |
| `TELEGRAM_LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `TELEGRAM_LLM_SYSTEM_PROMPT` | built in | Optional custom instructions for the Telegram assistant |
| `TELEGRAM_LLM_HISTORY_TTL` | `1800` | Seconds to retain each user's in-memory conversation context |
| `TELEGRAM_LLM_WORKERS` | `2` | Background workers for LLM replies, keeping Telegram webhooks responsive |
| `OIDC_CLIENT_SECRET` | _empty_ | Enables Makespace SSO; confidential value supplied by the Keycloak operator |
| `OIDC_ISSUER` | Makespace realm URL | Expected `iss` value and provider logout base URL |
| `OIDC_DISCOVERY_URL` | Makespace discovery URL | Provider endpoints and JWKS metadata |
| `OIDC_CLIENT_ID` | `manavote` | Confidential Keycloak client identifier |
| `OIDC_REDIRECT_URI` | generated from request | Exact HTTPS callback registered for the Keycloak client |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | generated from request | Exact HTTPS destination registered for provider logout |
| `OIDC_REQUIRED_GROUP` | `members-active` | Keycloak group required to sign in; set empty to disable this membership check |

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

### Telegram MCP commands

The bot can act as a restricted MCP client. Configure `MCP_API_KEY`,
`TELEGRAM_MCP_URL`, and `TELEGRAM_MCP_ALLOWED_USER_IDS`, then use:

```text
/mcp
/mcp tools
/mcp current_budget
/mcp list_proposals status=active limit=5
/mcp call current_budget
/mcp call list_proposals {"status":"active","limit":5}
```

The short `key=value` form is recommended for Telegram users. JSON and the
explicit `call` form remain available for automation and complex arguments.
The client performs the MCP initialize/initialized lifecycle handshake and supports
server-issued `Mcp-Session-Id` values for stateful HTTP MCP servers.

For the friendliest experience, set `TELEGRAM_LLM_API_KEY` and
`TELEGRAM_LLM_MODEL`. Linked members can then send ordinary messages such as
“What is the current budget?” or “Show me the five active proposals.” The model
receives the MCP tool definitions and calls the appropriate tools automatically;
slash commands remain available as a deterministic fallback. The API must implement
the OpenAI-compatible `/chat/completions` tool-calling contract.

The assistant remembers the last few messages for 30 minutes by default, so users
can ask follow-up questions. Send `forget`, `reset conversation`, or `start over` to
clear that context. Write tools are not executed immediately: the assistant must ask
for confirmation, and the user must answer `confirm`, `yes`, `do it`, or `go ahead`.
The confirmation is bound to the exact tool and arguments originally proposed; if
the model changes either, the new action requires another confirmation.
Send `cancel` or `never mind` to discard a pending action.

Natural-language replies run in a bounded background worker pool so Telegram receives
an immediate webhook acknowledgement instead of retrying during a slow model/tool
request. Telegram `update_id` values are deduplicated before work is submitted.

Members with a linked numeric Telegram user ID are allowed automatically. The
allowlist can grant access to additional numeric user IDs; never put a public chat
ID or Telegram username in it because MCP tools have administrative access.
Commands are private-chat-only by default; leave
`TELEGRAM_MCP_ALLOW_GROUPS=false` unless exposing MCP results in a group is intended.

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
- Auto: Runs every 24 hours via APScheduler (if installed), keeps the last 7 days of backups
- Database backup files: `backups/<db_name>_YYYYMMDD_HHMMSS.db` (for example `backups/app_20260513_120000.db`)
- Uploads backup files: `backups/uploads_YYYYMMDD_HHMMSS.zip`
- Default backup directory: `<repo>/backups` (resolved from app repository root)
- Docker note: the default compose file does **not** mount `backups/` as a named volume, so backup files are not persisted across container recreation unless you add a bind mount or dedicated volume for `/app/backups`.

## Testing
```bash
pytest -q
npm test
npm run build
```

Focused regression slice for the ongoing route decomposition:

```bash
pytest -q tests/test_blueprint_registration.py tests/test_blueprint_endpoint_aliases.py tests/test_api_helpers.py tests/test_production_config.py
```
## Makespace SSO

Manavote supports OpenID Connect Authorization Code login with PKCE through the
Makespace Keycloak realm. Set `OIDC_CLIENT_SECRET` in the server environment (or
secret manager) to enable the **Login with Makespace SSO** button. Never expose
this value to browser-side code. The remaining defaults are shown in
`sample.env`; override them only when the Keycloak client changes.

Register this login redirect URI in Keycloak:

```
https://manavote.mksmad.org/auth/callback/keycloak
```

For provider logout redirection, also allow
`https://manavote.mksmad.org/login` as a valid post-logout redirect URI. The app
requests `openid profile email`, validates the ID token using the provider's
discovery metadata/JWKS, and creates a local member keyed by the stable `sub`
claim. Membership in the `admins` group controls the local administrator flag.
The `members-active` group is required by default, preventing former or inactive
members from signing in. Tokens and the confidential client secret are not
stored in browser sessions.

### Keycloak client checklist

1. Configure `manavote` as a **confidential** client with Standard Flow enabled.
2. Register `https://manavote.mksmad.org/auth/callback/keycloak` as an exact
   valid redirect URI.
3. Register `https://manavote.mksmad.org/login` as a valid post-logout redirect
   URI.
4. Include a `groups` array in the ID token: `members-active` grants access and
   `admins` grants local administrator privileges.
5. Include `telegram_handle` when it is available.
6. Deliver the generated client secret through the deployment secret manager,
   never through source control or client-side code.

Restart Manavote after changing its environment. The SSO button is hidden until
`OIDC_CLIENT_SECRET` is non-empty.

### Account and session behavior

- The immutable Keycloak `sub` identifies a local member. Profile changes do not
  create another account.
- A first-login username collision gets a numeric suffix. Manavote never silently
  attaches an SSO identity to an existing password account.
- The `admins` group is synchronized at every login, including removal of local
  administrator access when the group is removed.
- Access and refresh tokens are discarded after the server-side callback.
  Manavote does not need to refresh tokens because it makes no subsequent
  Keycloak API calls.
- Password login remains available. Only SSO-created sessions use provider
  logout.

### Troubleshooting

- **SSO button missing:** set `OIDC_CLIENT_SECRET` in the running process and
  restart it.
- **Invalid redirect URI:** compare `OIDC_REDIRECT_URI` byte-for-byte with the
  registered URI, including scheme and path.
- **403 after callback:** ensure the ID token contains `groups` with
  `members-active`, or set `OIDC_REQUIRED_GROUP=` to disable this check.
- **Logout redirect rejected:** register the exact
  `OIDC_POST_LOGOUT_REDIRECT_URI` in Keycloak.
- **Token validation failure:** verify discovery/issuer settings, system clock,
  client ID, and client secret. Do not replace discovery/JWKS validation with the
  static realm public key.
