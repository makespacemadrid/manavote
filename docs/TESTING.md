# Testing Guide

## Run everything

```bash
pytest -q
npm test
```

## Targeted regression packs

```bash
pytest -q tests/test_template_guards.py tests/test_production_config.py tests/test_app_startup.py tests/test_startup_policy.py tests/unit/test_settings_service.py tests/unit/test_vote_repository_contract.py
```

### Frontend regression checks

```bash
pytest -q tests/test_react_frontend.py
npm test
```

- The Python integration pack renders the Jinja navigation, decodes its React hydration props, checks member/admin link visibility, verifies the active-page accessibility state, and requests fallback assets through Flask.
- Vitest renders the React navigation component and checks its semantic navigation label, mobile-menu relationships, collapsed state, and current-page marker.
- Run `npm run build` when changing JSX, Vite configuration, or shared styles; the production files are written to `static/react`.
- Backend-only environments may use the committed fallback assets, but CI and production images should build the React bundle.

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
- `include_unlinked=true` classification coverage (`linked|missing_user_id|unlinked`)
- `include_unlinked=false` filtered-list coverage (linked-only rows, `link_state=linked`)

```bash
pytest -q tests/unit/test_telegram_link_diagnostics.py
```

Covers the shared SQL classification helper (`LINKED_CONDITION_SQL`, `link_state_case_sql`)
backing the `link_state`/`include_unlinked` behavior above.

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

Automatic (non-admin-triggered) backups emit the same kind of structured events under
distinct event names, covered separately:

```bash
pytest -q tests/test_backup_service.py tests/test_app_startup.py
```

- `tests/test_backup_service.py::TestScheduledBackupJob` — the daily APScheduler jobs
  emit `scheduled_backup_created`/`scheduled_backup_failed` (with `pruned_count`/`error`)
  for both the DB and uploads backups, and `start_scheduler` wires both jobs correctly.
- `tests/test_app_startup.py::TestCheckAutoBackupAuditEvents` — the startup auto-backup
  check emits `startup_backup_created`/`startup_backup_failed`, attributes a failure to
  the right `backup_type` (`db` vs `images`), and only writes the `.last_backup` marker
  on full success.

## MCP-focused checks

```bash
pytest -q tests/test_mcp_server.py
```

Covers MCP auth, tool discovery, create-tool happy paths, and key negative-path contracts:
- validation failures (`-32602`)
- conflict class (`-32010`)
- not-found class (`-32004`)
- `list_user_statistics` success shape, admin-only `include_email` opt-in, invalid
  pagination, and budget/poll/group-purchase ranking and filtering

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
- `list_user_statistics` parity: success shape, invalid `limit`, and the `include_email`
  opt-in (and its invalid-value rejection) between REST and MCP

## Telegram webhook vote-response checks

```bash
pytest -q tests/unit/test_telegram_webhook_helpers.py tests/unit/test_telegram_link_service.py
```

Covers Telegram vote command/callback helper behavior:
- linked-account guidance text for `link_required` failures
- shared callback/poll message mappings for common vote rejection reasons
- callback fallback text for unknown reasons
- poll-command dispatch path returns linked-account guidance when vote handlers return `link_required`
- group `@mention`/reply/`bot_command` addressing (`is_natural_language_message`), using
  UTF-16 entity offsets and ignoring mentions/commands aimed at other bots
- forum-topic detection (`is_configured_forum_topic`) and recovering `message_thread_id`
  from `reply_to_message` when it is absent on the outer message
- `/reset` dispatch clearing the natural-language conversation, group-chat `/link`
  credential rejection, and `showvote`/vote callback dispatch routing

Telegram link-service unit coverage:
- unlink persistence behavior
- `/link` invalid-format rejection
- `/link` success-path linkage persistence (with and without a public Telegram username)
- duplicate `telegram_user_id` rejection (`already_linked`)

## Natural-language Telegram + MCP checks

Run the complete focused pack for the assistant branch:

```bash
pytest -q \
  tests/unit/test_telegram_agent.py \
  tests/unit/test_telegram_access_service.py \
  tests/unit/test_bounded_executor.py \
  tests/unit/test_telegram_webhook_helpers.py \
  tests/test_telegram_client.py
pytest -q tests/test_app_functionality.py -k telegram_webhook
```

Coverage is split by responsibility:

- `tests/unit/test_telegram_agent.py`
  - member/admin MCP tool visibility and sensitive read-tool restrictions
  - OpenAI-compatible tool-call/result round trips
  - explicit `/confirm` and `/cancel`, confirmation expiry, and MCP error formatting
  - per-chat/per-user pending-action isolation and invalid tool arguments
  - pending actions and conversation history both survive a fresh connection (simulating
    a different worker) and conversation history stays bounded to the most recent turns
- `tests/unit/test_telegram_access_service.py`
  - live allowlist construction from `members.telegram_user_id`
  - linked administrator resolution, invalid IDs, and link changes without restart
- `tests/unit/test_bounded_executor.py`
  - active+pending capacity, full-queue rejection, and capacity release
- `tests/unit/test_telegram_webhook_helpers.py`
  - Telegram `update_id` retry deduplication and bounded eviction
  - `/reset`, deterministic vote/link command dispatch, and callback parsing
- `tests/test_telegram_client.py`
  - Telegram `ok` response handling, long-message chunking, and fail-fast delivery
  - temporary thinking-message ID capture, topic propagation, and deletion
- `tests/test_app_functionality.py -k telegram_webhook`
  - authenticated Flask webhook routes, proposal/poll commands, callbacks, linking,
    edited messages, strict linked-vote policy, and malformed requests

No live Ocabra or Telegram credentials are required for this pack. HTTP/model calls
are mocked; use an explicitly configured test bot only for optional manual smoke tests.

## Poll auto-close + Telegram result message checks

```bash
pytest -q tests/unit/test_poll_closing.py
```

Covers:
- `close_expired_polls` closes only expired open polls.
- `build_poll_results_message` includes title, totals, and graph output.
- invalid/malformed `options_json` fallback messaging for closed-poll summaries.

## Telegram link lifecycle audit checks

```bash
pytest -q tests/test_app_functionality.py -k "unlink_telegram_action_emits_audit_event or telegram_settings_unlink_action_emits_audit_event or telegram_webhook_link_command_emits_audit_event"
```

Covers structured audit-log emission on:
- admin-triggered Telegram unlink
- member self-service Telegram unlink
- Telegram `/link` command success path

`last_linked_at`/`last_unlinked_at` metadata coverage:

```bash
pytest -q tests/unit/test_telegram_link_service.py tests/test_oidc_auth.py -k "last_linked or link"
```

- `tests/unit/test_telegram_link_service.py` — `/link` sets `last_linked_at`; unlink sets
  `last_unlinked_at`.
- `tests/test_oidc_auth.py::test_oidc_member_last_linked_at_only_bumps_when_telegram_id_changes`
  — an OIDC login only bumps `last_linked_at` when the claims' Telegram identity is newly
  set or actually changes, not on every login with the same value.

## OpenID Connect regression tests

Run the focused Makespace SSO regression pack with:

```bash
pytest -q tests/test_oidc_auth.py
```

It covers additive migration and `sub` uniqueness, disabled SSO behavior, public
callback selection, required-group enforcement, missing identity claims, session
rotation without token persistence, provider logout, idempotent claim updates,
administrator removal, and local username collisions.

## Other regression packs

Not part of a themed pack above, but each exercises real, otherwise-undocumented behavior:

- `tests/test_backup_service.py` — unit-level backup scheduler, upload-backup, and
  database-backup behavior (distinct from the admin-observability pack above, which
  covers the admin-panel/audit-event layer on top of this).
- `tests/test_group_purchases.py` — group-purchase creation, per-member quantities,
  proportional shared-cost splitting, and lifecycle migrations.
- `tests/test_budget_admin_refactor.py` — admin budget-tab behavior after the `/budget`
  route split.
- `tests/test_language.py` — language switching, translation coverage, proposal
  filters/status, and calendar/budget chart data.
- `tests/test_email_accounts.py` — email-based login and account-linking.
- `tests/test_proposal_service.py`, `tests/test_proposal_edit_route.py`,
  `tests/test_proposal_vote_mode.py`, `tests/test_settings_layout.py`,
  `tests/test_translation_coverage.py`, `tests/test_main_route_helpers.py`,
  `tests/test_blueprint_endpoint_aliases.py`, `tests/test_blueprint_registration.py`,
  `tests/test_db_fixture.py`, `tests/test_docker_configuration.py`,
  `tests/unit/test_admin_audit_helpers.py`, `tests/unit/test_services.py` — narrower unit
  and route-level coverage for their namesake area; run individually with
  `pytest -q <path>` or rely on the full `pytest -q` run at the top of this document.
