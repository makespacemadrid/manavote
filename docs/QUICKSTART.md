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
| `TELEGRAM_BOT_USERNAME` | _empty_ | Bot username used for exact group mention/reply matching |
| `TELEGRAM_CHAT_ID` | _empty_ | Telegram target chat |
| `TELEGRAM_THREAD_ID` | _empty_ | Optional Telegram topic/thread id for forum chats |
| `TELEGRAM_ADMIN_ID` | _empty_ | Optional Telegram user/chat id for poll test messages from admin panel |
| `TELEGRAM_WEBHOOK_SECRET` | _empty_ | Secret path segment used by Telegram webhook endpoint for command/inline-button poll voting |
| `OCABRA_CHAT_URL` | _empty_ | Optional OpenAI-compatible chat-completions URL enabling natural-language Telegram + MCP |
| `OCABRA_API_KEY` | _empty_ | Optional bearer token for the Ocabra endpoint |
| `OCABRA_MODEL` | `ocabra` | Model used by the natural-language Telegram assistant |
| `OCABRA_TIMEOUT_SECONDS` | `60` | Timeout for each model request |
| `TELEGRAM_CONFIRM_TTL_SECONDS` | `300` | Seconds before a pending mutating MCP action expires |
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

Natural-language assistant access does not require a separate Telegram allowlist.
ManaVote reads linked `members.telegram_user_id` values from the database for each
message, so account links, unlinks, and administrator-role changes apply immediately.

### Enable natural-language Telegram management

1. Configure `MCP_API_KEY`. `MCP_SERVER_ENABLED` is needed only for external MCP
   clients; the in-process Telegram integration does not require the network server.
2. Set `OCABRA_CHAT_URL` to the model server's OpenAI-compatible
   `/v1/chat/completions` endpoint; set `OCABRA_API_KEY` when that server requires it.
3. Set `OCABRA_MODEL` to a model that supports OpenAI-style function/tool calling.
4. Link a member by sending `/link <app_username> <app_password>` in a private chat.
   Never send credentials in a group. ManaVote rejects group-chat link attempts and
   asks Telegram to delete every credential-bearing `/link` message after receipt.
5. Ask a question such as `What is our current budget?`. The bot displays a temporary
   thinking message and replaces it with the completed response. In a group, mention
   the bot or reply to one of its messages; set `TELEGRAM_BOT_USERNAME` to the bot's
   username for exact mention matching when Telegram privacy mode is disabled.
6. For an administrator mutation, inspect the proposed arguments and send `/confirm`
   within the configured TTL, or `/cancel`. Use `/reset` to clear the conversation.

If the bot answers that the assistant is not configured, verify both
`OCABRA_CHAT_URL` and `MCP_API_KEY`. If it reports that it is busy, wait for queued
model requests to finish and retry; webhook retries are deduplicated automatically.

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
