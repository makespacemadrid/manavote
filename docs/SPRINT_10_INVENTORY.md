# Sprint 10 — Route Ownership Inventory

Reviewed: 2026-10-08. Complete: 777 Python tests and frontend test/build passed.

This records every `legacy.*` attribute used by the eight route blueprints, including
local aliases re-read on each request. It distinguishes intentional adapters from
misplaced SQL/domain behavior. [SPRINTS.md](SPRINTS.md#sprint-10-completed-2026-10-08--architecture-boundary-closure)
owns status; [DIAGRAMS.md](DIAGRAMS.md#request-path-web-page-load) shows the read path.

## Adapter inventory

Keep these boundaries where they preserve configuration, Flask context, initialization,
or compatibility/patch points. References to a service through a wrapper are not proof
that its domain logic still lives in the route layer. Runtime instances are retained;
this sprint does not introduce a second executor or deduplicator.

| Attribute | Classification | Owner / reason retained | Consumers |
|---|---|---|---|
| `ADMIN_API_KEY` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `api_routes` |
| `DB_PATH` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `admin_routes` |
| `TELEGRAM_ADMIN_ID` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `admin_routes` |
| `TELEGRAM_BOT_TOKEN` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `proposal_routes`, `telegram_routes` |
| `TELEGRAM_BOT_USERNAME` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `telegram_routes` |
| `TELEGRAM_CHAT_ID` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `proposal_routes`, `telegram_routes` |
| `TELEGRAM_THREAD_ID` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `proposal_routes`, `telegram_routes` |
| `TELEGRAM_WEBHOOK_SECRET` | Runtime configuration | environment/app setup; preserve request-time reads and existing test patches | `telegram_routes` |
| `TelegramClient` | Compatibility re-export | integrations.telegram_client; retained injection/patch boundary | `proposal_routes`, `telegram_routes` |
| `_telegram_agent_executor` | Shared runtime state | integrations.bounded_executor; per-process singleton and exit shutdown | `telegram_routes`, `admin_routes` |
| `_telegram_member_admission` | Shared runtime state (Sprint 11) | integrations.member_admission; process-local singleton keyed by linked member identity | `telegram_routes`, `admin_routes` |
| `_telegram_jobs` | Shared runtime state (Sprint 15) | integrations.assistant_jobs; process-local owned futures and aggregate telemetry | `telegram_routes`, `admin_routes` |
| `_telegram_update_deduplicator` | Shared runtime state | integrations.telegram_webhook; shared DB-backed deduplication | `telegram_routes` |
| `admin_required` | Compatibility re-export | web.decorators.admin_required | `admin_routes` |
| `app` | Runtime/context adapter | web.app_setup.app; logging/config and established test patch points | `admin_routes`, `api_routes`, `poll_routes`, `proposal_routes`, `telegram_routes` |
| `build_poll_results_message` | Compatibility adapter | poll_service.build_poll_results_message | `admin_routes`, `poll_routes` |
| `calculate_min_backers` | Compatibility re-export | budget_service.calculate_min_backers | `proposal_routes` |
| `can_record_proposal_vote` | Policy adapter | voting_mode_service | `proposal_routes`, `telegram_routes` |
| `check_over_budget_proposals` | Runtime/composition adapter | ProposalService.check_over_budget_proposals | `admin_routes`, `proposal_routes` |
| `close_expired_polls` | Compatibility adapter | poll_service.close_expired_polls | `admin_routes`, `poll_routes` |
| `detect_image_type` | Compatibility re-export | web.routes.helpers.main_helpers | `group_purchase_routes`, `proposal_routes` |
| `ensure_db_ready` | Initialization adapter | startup/db.migrations; retained for existing schema/bootstrap contract | `admin_routes`, `group_purchase_routes`, `poll_routes` |
| `get_base_url` | Request-context adapter | settings_repo plus request.host_url fallback | `group_purchase_routes`, `proposal_routes`, `telegram_routes` |
| `get_current_budget` | Compatibility adapter | BudgetRepository.current_budget; duplicate SQL removed in this slice | `admin_routes`, `proposal_routes` |
| `get_db` | Initialization/runtime adapter | db.connection; keep migration readiness and patched DB_PATH behavior | `admin_routes`, `api_routes`, `auth_routes`, `coin_routes`, `group_purchase_routes`, `poll_routes`, `proposal_routes`, `telegram_routes` |
| `get_member_count` | Compatibility adapter | MemberRepository.count; duplicate SQL removed in this slice | `proposal_routes` |
| `get_poll_vote_mode` | Policy adapter | voting_mode_service; request-time setting reads | `api_routes` |
| `get_proposal_vote_mode` | Policy adapter | voting_mode_service; request-time setting reads | `api_routes`, `proposal_routes` |
| `get_setting_float` | Compatibility adapter | get_setting_value with existing numeric fallback | `admin_routes` |
| `get_setting_value` | Compatibility adapter | SettingsRepository.get_value | `admin_routes`, `poll_routes` |
| `get_thresholds` | Compatibility adapter | SettingsRepository.get_thresholds | `admin_routes`, `proposal_routes` |
| `get_vote_counts` | Compatibility adapter | VoteRepository.get_counts; cursor signature retained | `proposal_routes` |
| `is_registration_enabled` | Policy adapter | voting_mode_service; request-time setting reads | `admin_routes`, `auth_routes` |
| `is_telegram_poll_voting_enabled` | Policy adapter | voting_mode_service; request-time setting reads | `poll_routes` |
| `is_web_poll_voting_enabled` | Policy adapter | voting_mode_service; request-time setting reads | `poll_routes` |
| `is_web_proposal_voting_enabled` | Policy adapter | voting_mode_service; request-time setting reads | `proposal_routes` |
| `log_proposal_vote_event` | Logging adapter | proposal_vote_recording_service | `proposal_routes` |
| `process_proposal` | Runtime/composition adapter | ProposalService; injects Telegram client/base URL and runs pending approvals | `proposal_routes` |
| `process_telegram_link_command` | Request/integration adapter | telegram_link_service; signed browser link needs Flask secret/base URL; logs lifecycle result | `telegram_routes` |
| `process_telegram_proposal_vote_command` | Composition adapter | telegram_command_service; injects vote recording and logger | `telegram_routes` |
| `process_telegram_vote_callback` | Composition adapter | telegram_command_service; injects vote recording and messaging | `telegram_routes` |
| `process_telegram_vote_command` | Composition adapter | telegram_command_service; injects settings/connection/messaging/logger | `telegram_routes` |
| `record_proposal_vote` | Composition adapter | proposal_vote_recording_service; injects connection/settings/processing/logger | `proposal_routes` |
| `require_linked_telegram_for_votes` | Policy adapter | voting_mode_service; request-time setting reads | `api_routes` |
| `send_telegram_admin_test_message` | Integration adapter | telegram_messaging_service; runtime admin destination | `admin_routes` |
| `send_telegram_message` | Integration adapter | telegram_messaging_service; injected runtime bot/chat/thread settings | `admin_routes`, `api_routes`, `group_purchase_routes`, `poll_routes`, `proposal_routes` |
| `sync_telegram_webhook` | Integration adapter | telegram_messaging_service; configured credentials and base URL | `admin_routes` |

## Delivered slice 1 — Budget and proposal-list reads

- `/budget`: `budget_service.build_budget_page` owns timeline, pending-release, and
  pagination calculations; BudgetRepository and ProposalRepository own calendar/daily queries.
- `/proposals`: `proposal_page_service.build_proposal_page` owns ages, vote requirements,
  running balances, and member view data. Repositories own list predicates, chip totals,
  settings, member counts, and vote reads.
- Duplicate SQL in `get_current_budget`, `get_member_count`, and `get_vote_counts` now
  delegates to the existing repositories. Public wrapper signatures remain compatible.
- Routes keep login checks, request/session arguments, view-policy adapters, rendering,
  and connection cleanup. Services borrow the connection; routes close it in `finally`.
- No filter, threshold, monetary, REST/MCP, or lifecycle semantics were changed. In
  particular, expensive-list membership and expensive-chip totals retain their distinct
  existing predicates; unknown filters still display all proposals.

## Delivered slice 2 — Purchase flags and proposal/comment actions

- `proposal_actions_service` owns the approved-only purchase flag rule, active-only
  proposal deletion, owner/admin deletion authorization, and admin-only comment editing/deletion.
- ProposalRepository, VoteRepository, and CommentRepository own writes. Proposal
  deletion removes its votes/comments atomically; failed writes roll back before raising.
- Routes retain login checks, POST-only mutation endpoints, redirects, translated flash
  messages, and `finally` cleanup. Missing rows, invalid status, blank comment edits,
  and role rejection retain their existing response behavior.
- Existing purchase/unpurchase routes allow any signed-in member on an approved
  proposal; this extraction preserves that policy rather than adding an owner/admin gate.
- Services emit safe actor/proposal/comment metadata after successful writes; comment
  contents are not logged. Direct and HTTP tests cover permissions, status, side effects,
  rollback, cleanup, missing rows, and blank-edit behavior.

## Delivered closure slices — Lifecycle, identity, and administration

- Vote withdrawal and approval undo live in `proposal_actions_service`: withdrawal
  affects only the actor's vote; undo restores ledger/settings and clears processed
  and purchased timestamps before ordered reprocessing callbacks. Missing-row/no-op,
  processed-row, authorization, and HTTP behavior are preserved.
- Proposal creation/edit/detail and comment addition use proposal/comment/vote/member
  repositories and proposal action/read-model services. Creation keeps its creator vote
  and processing/notification sequence; edits keep the automatic basic-supplies comment.
- `auth_service` owns credential migration, registration, password/email validation,
  and OIDC provisioning. MemberRepository preserves username-first login, email
  attachment only to an unbound identity, collision suffixes, and group-role synchronization.
- API lookups, proposal filters, link diagnostics, statistics, and poll lists use
  repositories/read-model services. `member_queries` owns shared statistics/link query
  composition with compatibility exports for existing REST/MCP imports. REST fields, errors, and pagination are unchanged.
- Poll read models and additive/clear vote decisions live in `poll_page_service`;
  PollRepository owns options/results/voter queries. Channel checks remain request-time adapters.
- QR provisioning and rotation/activation live in `coin_service`; CoinRepository owns
  token lookup and labels. Printed-label invalidation and replenish-token removal are preserved.
- GroupPurchaseRepository and `group_purchase_service` own purchase/selection/payment
  persistence, owner/admin rules, creator-only status/payment actions, and proportional
  shared-cost allocation. Uploads, translated notifications, and rendering remain HTTP adapters.
- `admin_actions_service` owns administrator use cases with explicitly injected runtime
  dependencies; `admin_page_service` assembles page data. The blueprint owns session
  changes, flashes, tab context, and rendering. Audit functions live in `audit_service`
  with compatibility exports in the former helper module.
- Bootstrap DDL/defaults/migration checks moved to `app/db/initialization.py`.
  `main_routes.init_db`/`ensure_db_ready` preserve paths, startup policy, and patch points.
- Two additional Telegram webhook SQL reads now use member/poll repositories. Job
  dispatch, live-principal lookup, model/delivery callbacks, and the singleton executor
  remain intentional integration adapters; Sprint 11 changes admission in that boundary.

## Closure evidence and retained adapters

- All 45 Sprint 10 `legacy.*` attributes remain classified above. Runtime reads and
  established integration patch points are still evaluated at request time.
- No route module calls SQL `execute`, `executemany`, or `executescript`; an AST boundary
  check guards every `*_routes.py`, including Telegram and main compatibility routes.
- Extracted services do not import Flask or `app.web`. Direct checks exercise identity,
  purchase allocation, additive votes, admin protections, budget rollback, and lifecycle
  callbacks alongside the existing HTTP regression packs.
- Services borrow connections; HTTP adapters close them. Initialization closes its own
  connection even when production bootstrap refuses to proceed.
- Group-purchase parsing exports and audit helper exports remain for compatibility;
  tests now target their service owners. Legacy SQL-source tests now exercise behavior.
- Test setup selects the session database before importing the application; the
  per-test isolation fixture updates connection and compatibility runtime paths together.

The full-suite result and sprint closure are recorded in [SPRINTS.md](SPRINTS.md).
