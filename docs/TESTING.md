# Testing Guide

This guide owns executable test commands and the map from suites to responsibilities.
It does not redefine expected product or API behavior; failures should be interpreted
against [`SPEC.md`](SPEC.md) and [`APIDOC.md`](APIDOC.md).

## Contents

- [Run everything](#run-everything)
- [Documentation integrity](#documentation-integrity)
- [Core and frontend regression packs](#targeted-regression-packs)
- [REST API](#api-focused-checks)
- [Admin backup observability](#admin-backup-observability-checks)
- [Koins and ledger administration](#koins-and-ledger-administration-checks)
- [MCP](#mcp-focused-checks)
- [Voting settings REST/MCP parity](#voting-settings-restmcp-parity-checks)
- [Telegram webhook voting](#telegram-webhook-vote-response-checks)
- [Natural-language Telegram and MCP](#natural-language-telegram--mcp-checks)
- [Poll auto-close and Telegram results](#poll-auto-close--telegram-result-message-checks)
- [Telegram link lifecycle](#telegram-link-lifecycle-audit-checks)
- [OpenID Connect](#openid-connect-regression-tests)
- [Other regression packs](#other-regression-packs)

## Run everything

```bash
pytest -q
npm test
```

Operator-facing meanings for the reason codes and structured events exercised below are
documented in [`OPERATIONS.md`](OPERATIONS.md).

## Documentation integrity

```bash
pytest -q tests/test_documentation.py
```

This check verifies that relative Markdown files and heading fragments resolve, every
document is reachable from [`INDEX.md`](INDEX.md), and every variable in `sample.env`
appears in the Quick Start configuration reference. Add new documentation beneath
`docs/` to the map directly or link it from a document that is already reachable.

## Targeted regression packs

```bash
pytest -q tests/test_template_guards.py tests/test_production_config.py tests/test_app_startup.py tests/test_startup_policy.py tests/unit/test_settings_service.py tests/unit/test_vote_repository_contract.py
```

### Sprint 10 read-path ownership

```bash
pytest -q tests/unit/test_page_read_services.py tests/test_budget_admin_refactor.py tests/test_language.py tests/test_app_functionality.py
```

- Direct service tests exercise real migrated SQLite repositories for every proposal-list filter, exact 30-day boundaries, member votes, thresholds, chip totals, and running balances.
- Budget tests cover pending-release vs. all approval totals, cash signs, calendar sorting/pagination, and empty histories.
- Flask checks retain authentication/rendering/vote-policy behavior and verify database cleanup when read services fail. The former approval SQL-source assertion now checks repository results.
- [SPRINT_10_INVENTORY.md](SPRINT_10_INVENTORY.md) records retained adapters and delivered owners.

### Sprint 10 proposal action ownership

```bash
pytest -q tests/test_proposal_actions.py tests/test_app_functionality.py tests/test_proposal_edit_route.py
```

- Direct/HTTP action tests cover approved-only purchase flags, active-only owner/admin proposal deletion, and admin-only comment editing/deletion.
- Verify dependent vote/comment removal, atomic rollback on failed deletion, immutable comment identity/timestamps, blank-edit no-ops, unchanged budget, POST/login gates, redirects/flashes, and connection cleanup on service failures.
- Purchase endpoints retain the existing signed-in-member access policy; this refactor does not add an owner/admin restriction. Successful action logs contain metadata without comment contents.

### Sprint 10 remaining ownership and boundary guards

```bash
pytest -q tests/unit/test_sprint10_ownership.py tests/unit/test_auth_service.py tests/test_group_purchases.py tests/test_oidc_auth.py tests/test_email_accounts.py tests/test_coins.py
```

- AST guards prohibit SQL calls in every route module, Flask/web imports in extracted services, and service/web imports in repositories.
- Direct use-case checks cover admin self-protection, session-change results, budget-sign reprocessing, atomic rollback, poll creation/delivery/lifecycle, group debt allocation, creator permissions, additive/clear votes, and proposal detail/edit behavior.
- Withdrawal and undo tests use the real service, observe committed state before callbacks, and retain HTTP response/authorization checks; the former simulated undo test now invokes the owning service.
- Test database setup runs before application import. Per-test database isolation updates both connection and legacy runtime paths.

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
  - Telegram group/forum configuration without `TELEGRAM_BOT_USERNAME` emits the stable
    `missing_bot_username_for_group` warning without false positives for private chats.
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

## Koins and ledger-administration checks

```bash
pytest -q tests/test_coins.py tests/test_translation_coverage.py
```

This pack covers seeded and administrator-created items, member ledger movements,
idempotency, balances and rankings, per-item consumption totals, QR labels and token
controls, inventory adjustments, and MCP koin actions. It also verifies that:

- the Koins page renders the sortable lifetime **Consumption by item** table;
- the admin Koins tab renders the recent-movement editor and emoji navigation labels;
- an administrator can correct a movement's item, member, type, quantity, and note;
- corrected deltas and `source = admin` are persisted; and
- non-administrators cannot use any koin-management endpoint, including ledger edits.

## MCP-focused checks

```bash
pytest -q tests/test_mcp_server.py
```

Covers MCP auth, tool discovery, create-tool happy paths, and key negative-path contracts:
- validation failures (`-32602`)
- conflict class (`-32010`)
- not-found class (`-32004`)
- internal application failures preserve the request ID, return generic `-32000` error
  text, and do not disclose database exception details
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
- `create_proposal` parity: missing fields, non-positive amount, unknown/non-positive
  `created_by` (classified as not-found on both interfaces, not invalid-params),
  invalid `basic_supplies`, and success shape
- MCP proposal attachment coverage: URL and generated image-filename persistence,
  upload-file contents, and rejection of malformed base64 image data
- `create_poll` parity: question/option bounds (short question, too few/many options,
  an over-long option) and success shape

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
pytest -q tests/test_telegram_natural_language_webhook.py
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
- `tests/test_telegram_natural_language_webhook.py`
  - end-to-end: drives the real `POST /telegram/webhook/<secret>` route (not just
    `telegram_agent.answer()` directly) with only the outbound Telegram client and the
    OpenAI-compatible model response mocked
  - unlinked senders are ignored without enqueueing work; linked senders get a thinking
    message that is deleted after a real tool-call round trip and final reply delivery
  - a full assistant queue returns the busy notice and still cleans up the thinking
    message; a duplicate `update_id` is acknowledged without repeating the work
  - a linked member can request a specific proposal by natural language; the real MCP
    result supplies distinct `proposal_url`, `image_url`, and external-reference `url`
    fields, the final Telegram reply includes all requested links, and a referenced
    `image_url` is delivered through Telegram as a photo in the originating chat/thread
  - an administrator's propose → `/confirm` flow executes exactly one MCP write, and the
    same flow with the admin role removed between the two steps executes zero
  - structured job logs correlate `update_id`, chat/member identity, queue wait, model
    latency, tool name, job duration, and stable completion/rejection reason codes

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

## Sprint 11 assistant member admission

```bash
pytest -q tests/unit/test_member_admission.py tests/unit/test_bounded_executor.py tests/test_telegram_natural_language_webhook.py tests/unit/test_telegram_agent.py
```

- Direct checks synchronize concurrent acquires, exercise configured limits and startup
  rejection, and verify reusable admission after worker success/failure, global rejection,
  submit errors, inline completion, and queued cancellation. Releasing an old lease twice
  cannot release a newer reservation.
- Flask tests cover concurrent webhook requests, same-member cross-chat rejection,
  other-member capacity, update deduplication, English/Spanish responses without thinking
  or model/MCP calls, cancellation cleanup, and every worker/delivery/submit failure path.
- Busy `/confirm` and `/cancel` preserve pending mutations; retry cancellation bypasses
  the model. Existing confirmation success, actor/role changes, and mutation audits remain covered.

## Assistant safety regressions

Run `pytest -q tests/unit/test_assistant_safety.py tests/unit/test_telegram_agent.py tests/test_telegram_natural_language_webhook.py` for UTF-8/context boundaries, complete
history groups, configured credentials/sensitive fields, durable history, multi-round
tool payloads, localized rejection, admission release, and safe failure logs. Provider
and Telegram calls are mocked.

## Proposal contracts and vote-policy matrix

Run `pytest -q tests/test_proposal_contracts.py tests/test_proposal_service.py tests/test_proposal_actions.py tests/test_proposal_vote_mode.py` for public shapes/types/filters,
rejection envelopes, concurrent approval/undo, ledger failure rollback, over-budget
rechecks, reapproval semantics, and existing action permissions.

| Mode | Proposal list/detail controls | Poll web controls | Telegram deterministic vote guidance |
|---|---|---|---|
| `both` | Enabled | Enabled | Accepted for eligible linked members |
| `web_only` | Enabled | Enabled | Channel-disabled rejection |
| `telegram_only` | Hidden; proposal banner | Hidden | Accepted for eligible linked members |

The parameterized matrix in `tests/test_proposal_contracts.py` checks rendered controls
and deterministic guidance. Existing `tests/test_app_functionality.py` checks webhook
votes/callbacks and server-side channel rejection; `tests/test_proposal_actions.py`
retains owner/admin/status action coverage. These are coverage references, not new
Telegram vote tools or changed policy.

## Shared dialog and responsive browser checks

Run `pytest -q tests/test_admin_interface.py tests/test_language.py` for password form
fields/labels, administrator access, escaped member identity, bilingual headings, and
existing link/unlink timestamps in the configured local timezone.

For native keyboard/layout checks with installed Chromium and Node 24:

```bash
npm test
npm run build
MANAVOTE_UI_CAPTURE_DIR=/tmp/manavote-ui pytest -q tests/test_admin_interface.py
node scripts/check_dialogs.mjs /tmp/manavote-ui
```

The browser harness serves synthetic Flask test snapshots on localhost, checks password
opening/Tab/Shift-Tab/Escape/focus return/password clearing, shared danger confirmation
and feedback, cyan vote styling, and page overflow in both languages at 375/600/1280px.
It closes its server/browser and removes the temporary browser profile. It requires
localhost sockets; it never starts a production server or submits real domain changes.
Set `CHROMIUM` only when the executable has a different name. Build refreshes the
tracked frontend assets used by server-rendered pages.

## Queued cancellation and operator health regressions

Run `pytest -q tests/unit/test_assistant_jobs.py tests/unit/test_member_admission.py tests/unit/test_telegram_agent.py tests/test_telegram_natural_language_webhook.py tests/test_admin_interface.py` for owned futures, completion-before-attachment,
start/cancel races, capacity release, queued cancellation without model/MCP work,
webhook deduplication, pending-action ownership, relinking/role changes, running status,
cleanup failures, model/MCP/delivery telemetry, bounded summaries, and administrator-only
safe health responses. Network calls are mocked; concurrency uses real futures/SQLite.
