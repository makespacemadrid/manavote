# Testing Guide

## Run everything

```bash
pytest -q
```

## Targeted regression packs

```bash
pytest -q tests/test_template_guards.py tests/test_production_config.py tests/test_app_startup.py tests/test_startup_policy.py tests/unit/test_settings_service.py tests/unit/test_vote_repository_contract.py
```

### Coverage summary

- `tests/test_template_guards.py`
  - Admin template uses shared top navigation partial.
  - CSRF hidden input markup is well formed in key templates.
- `tests/test_production_config.py`
  - Startup fails when `FLASK_ENV=production` and `SECRET_KEY` is missing/default.
  - DB bootstrap fails on first startup in production if `ADMIN_BOOTSTRAP_PASSWORD` is missing.
- `tests/test_app_startup.py`
  - App startup sequencing remains deterministic and DB failures are fail-fast.
  - Optional startup jobs (scheduler/auto-backup) remain warning-only and can be skipped in `test` env.
- `tests/test_startup_policy.py`
  - Runtime policy flags are environment-aware (`test` disables optional startup jobs).
- `tests/unit/test_settings_service.py`
  - Enum-like setting reads are normalized with consistent fallback behavior.
- `tests/unit/test_vote_repository_contract.py`
  - Proposal-vote repository invariants (upsert replacement + vote counts) are enforced.


## API-focused checks

```bash
pytest -q tests/test_api_helpers.py tests/test_api_error_envelope.py tests/test_app_functionality.py -k "api or polls"
```

Covers API auth/content-type validation, error envelope consistency, proposal API validation, and poll API flows.
Also includes Telegram member-link diagnostics checks for both:
- `include_unlinked=true` classification coverage (`linked|missing_username|missing_user_id|unlinked`)
- `include_unlinked=false` filtered-list coverage (linked-only rows, `link_state=linked`)

## Admin backup observability checks

```bash
pytest -q tests/test_app_functionality.py -k "backup_download or backup_db or backup_images or preserves_requested_tab"
```

Covers admin backup/operator reliability regressions:
- backup download success + validation rejection paths
- tab-preserving redirects (`tab=settings`) and invalid-tab sanitization fallback (`tab=all`)
- structured audit events for:
  - download success/rejection
  - DB backup create/failure
  - image backup create/failure
- server-side admin tab propagation in POST-rendered admin responses

## MCP-focused checks

```bash
pytest -q tests/test_mcp_server.py
```

Covers MCP auth, tool discovery, create-tool happy paths, and key negative-path contracts:
- validation failures (`-32602`)
- conflict class (`-32010`)
- not-found class (`-32004`)

## Voting settings REST/MCP parity checks

```bash
pytest -q tests/test_voting_settings_parity.py
```

Covers contract-alignment scenarios for `PATCH /api/settings/voting` and MCP `update_voting_settings`:
- invalid `poll_vote_mode` rejection
- invalid `proposal_vote_mode` rejection
- invalid `telegram_require_linked_vote` rejection
- “no relevant changes provided” rejection
- successful update response-shape parity for shared setting keys
- member Telegram link-listing parity for REST `GET /api/members/telegram` and MCP `list_member_telegram_links` (`linked` + `link_state` diagnostics)
- out-of-range pagination rejection parity (`limit` upper bound enforcement)

## Telegram webhook vote-response checks

```bash
pytest -q tests/unit/test_telegram_webhook_helpers.py
```

Covers Telegram vote command/callback helper behavior:
- linked-account guidance text for `link_required` failures
- shared callback/poll message mappings for common vote rejection reasons
- callback fallback text for unknown reasons
- poll-command dispatch path returns linked-account guidance when vote handlers return `link_required`

Telegram link-service unit coverage:
- unlink persistence behavior
- `/link` invalid-format rejection
- `/link` success-path linkage persistence
- duplicate `telegram_user_id` rejection (`already_linked`)

## Telegram link lifecycle audit checks

```bash
pytest -q tests/test_app_functionality.py -k "unlink_telegram_action_emits_audit_event or telegram_settings_unlink_action_emits_audit_event or telegram_webhook_link_command_emits_audit_event"
```

Covers structured audit-log emission on:
- admin-triggered Telegram unlink
- member self-service Telegram unlink
- Telegram `/link` command success path
