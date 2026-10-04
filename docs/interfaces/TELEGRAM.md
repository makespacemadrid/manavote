# Telegram Interface Reference

This document owns ManaVote's Telegram command and natural-language assistant contract.
For webhook diagnostics and production reason codes, see
[`../OPERATIONS.md`](../OPERATIONS.md); for other integration surfaces, return to the
[interface index](../APIDOC.md).

## Contents

- [Bot commands](#bot-commands)
- [Natural-language assistant](#natural-language-telegram--mcp)

## Bot commands

- `/link` — begin passwordless Telegram account linking in a private bot chat. The bot
  returns a signed browser link that expires after 15 minutes. After signing in to
  ManaVote, the member explicitly confirms the Telegram identity. Legacy credential
  arguments are still accepted for compatibility and their message is deleted when
  possible, but the browser flow is the documented path.
- `/vote <poll_id> <option_number> [option_number...]` or `/vote <option_number>` — vote
  in polls, subject to `poll_vote_mode`. Multiple option numbers are accepted only with
  the explicit `poll_id` form. The two-token shorthand targets the latest open poll and
  remains single-option only. A multi-option vote on a single-select poll is rejected
  with reason `multiple_options_not_allowed`.
- `/pvote <proposal_id> <yes|no>` — vote on proposals (subject to `proposal_vote_mode`).
- If `telegram_require_linked_vote=true`, Telegram vote commands work only for linked
  accounts; unlinked users are told to send `/link` in a private bot chat.
- Proposal inline callback payload: `pvote:<proposal_id>:yes|no` (same policy path as `/pvote`).
- Without the optional natural-language configuration, non-command Telegram messages
  receive a configuration hint and have no poll or proposal vote side effects.

## Natural-language Telegram + MCP

The Telegram assistant exposes an explicit, deny-by-default subset of MCP tools.
`create_member` is never supplied to the model or callable through the Telegram adapter
because its arguments contain a password; member creation remains available through
authenticated MCP clients outside Telegram.

Accepted Telegram `update_id` values are stored in the application database with a
bounded retention window. Duplicate webhook deliveries are therefore suppressed across
application workers and restarts, before commands, votes, model calls, or MCP actions run.

For Telegram proposal and poll creation, `created_by` is not model-supplied. The adapter
binds it to the database member linked to the sender's Telegram ID and rechecks that
identity when the administrator confirms the action.
After a confirmed Telegram proposal is saved, the adapter publishes the same proposal
announcement and voting controls to the configured group/thread as web-created proposals.
If Telegram rejects that delivery, the confirmation response explicitly reports that the
proposal was saved but its group notification failed.

Pending mutation confirmations are stored in SQLite by chat and Telegram user. They
therefore survive application restarts and can be confirmed on a different worker; a
confirmation is atomically consumed before its MCP mutation executes.

This integration is inspired by Luis Rivera's
[`ocabra_telegram`](https://github.com/luisriverag/ocabra_telegram) project and adapts
its OpenAI-compatible conversational pattern to ManaVote's webhook and MCP runtime.

Set `OCABRA_CHAT_URL` to an OpenAI-compatible `/v1/chat/completions` endpoint and
configure `MCP_API_KEY` to enable natural-language messages. The webhook supplies
the ManaVote MCP tools to the model, executes requested tools locally, and returns
the final answer to Telegram. Users must link their account first. Linked members
receive read-only tools; mutating tools are exposed only to linked administrators.
Member access is limited to proposals, polls, group purchases, budget, and voting
settings (the read-only tool set). Member statistics and Telegram-link records are
admin-only even though those MCP tools are read-only.
The assistant allowlist is loaded automatically from non-null `members.telegram_user_id`
values on every incoming natural-language message. Linking, unlinking, or changing
an administrator role therefore takes effect without maintaining a separate
environment-variable allowlist or restarting the application.
Non-command messages from IDs outside that allowlist are acknowledged but ignored;
they are not placed on the model worker queue. `/help` and `/link` remain available.
In private chats every non-command message is eligible. In groups, the assistant
responds when a member addresses it with an `@mention` or replies to one of its
messages; other group conversation is ignored. `TELEGRAM_BOT_USERNAME` must be set
whenever the bot's Telegram privacy mode is disabled outside the configured forum
topic: without it, any `@mention` or `/command` entity in the group is treated as
addressed to this bot, including ones aimed at a different user or bot.
Assistant and command responses stay in the incoming forum topic when
`message_thread_id` is present. The forum topic selected by `TELEGRAM_CHAT_ID` and
`TELEGRAM_THREAD_ID` is treated as a dedicated assistant conversation, so linked
members can chat there without repeating the bot's `@mention` on every message.
The bot's group privacy mode must be disabled through BotFather for Telegram to
deliver those unmentioned messages; with privacy mode enabled, members must still
mention the bot or reply to one of its messages.
Mutating tool calls are never executed immediately: the administrator must send
`/confirm` within `TELEGRAM_CONFIRM_TTL_SECONDS` (default: 300) to execute the
pending action or `/cancel` to discard it. Telegram's group-chat forms
`/confirm@botname` and `/cancel@botname` are accepted as the same commands. Conversation
history and pending confirmations are isolated by both chat and Telegram user, so
members sharing a group chat do not share assistant state.
Configured natural-language requests run outside the webhook request thread so
Telegram receives an immediate acknowledgement while model and MCP rounds finish.
For accepted assistant requests, the bot posts a temporary `🤔 Thinking…` message
and deletes it after the final response has been delivered.
The worker pool has a bounded queue; when saturated, the bot asks the member to
retry shortly instead of accumulating an unbounded number of model requests.
Recent Telegram `update_id` values are deduplicated before dispatch, preventing
webhook retries from repeating model requests, votes, or confirmed MCP actions.
Responses longer than Telegram's message limit are split into readable chunks.
Commands such as `/link`, `/vote`, and `/pvote` continue to use their deterministic
handlers rather than the model.
Use `/reset` to clear only the requesting user's conversation and pending action.
