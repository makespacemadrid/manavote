# META — Retrospective: What ~300 Commits Ago Needed to Know

This project is 346 commits old as of this writing (`git log --oneline origin/main | wc -l`).
"300 commits ago" lands around commit **#47** — chronologically, right after the first
withdraw-vote feature and before the first CSRF token, the first password-hash
migration, the first `app/services/` module, the first test file worth calling a
regression suite, or any of `SPEC.md`/`APIDOC.md`/`IDEAS.md`/`STYLE.md` existed. This
document is what commit #47 would have wanted to read: real, dated evidence from this
repository's own history of decisions that were cheap to make early and expensive to
retrofit later, plus a few habits that paid for themselves once adopted and should have
started sooner.

This is not a criticism of the pace or judgment that got the project here — a
community-run budget-voting app iterating in public with real users is exactly the kind
of project where "ship it, fix it live" is often the right call. It's a note to whoever
starts the next project (or the next major surface on this one) with the unfair
advantage of already knowing how this one turned out.

## 1. Give every button/form a shared component before the second one exists

The withdraw-vote button alone took **six commits** to settle:
`ef39d0f` (add) → `9553386` (fix + relocate) → `8e34aed` (remove from dashboard,
restyle) → `0d604d2` (match vote-button style) → `795e404` (fix styling again) →
`5212258` (convert to a real `<button>` element). That thrashing happened because there
was no shared button component to reach for yet — each attempt hand-rolled its own
markup and styling.

The cost didn't stay contained to that one button: the 2026-08-27 UX/UI audit
(`IDEAS.md`) still found a real design system in place (`.btn`, `.vote-btn`, `.status`)
being routinely bypassed by one-off inline styles years later — the exact same failure
mode, just distributed across more templates by then. **A repo-wide button/badge/modal
component, established before the second form is written, is one of the cheapest
insurance policies available** — cheaper by orders of magnitude than the UX pass needed
to claw it back after dozens of templates have their own inline variants.

## 2. Any state a mutation depends on belongs in the database from the first line, not an in-memory dict

Telegram pending confirmations, update deduplication, and assistant conversation
history were all built as process-local in-memory structures. Fixing that — moving all
three to shared SQLite so they survive a restart and can't be routed to a process that
doesn't own them — was tracked as a **P0** item and wasn't closed until 2026-08-27,
long after the Telegram assistant had real users depending on `/confirm` actually
completing what it said it would.

This is a general shape, not a Telegram-specific one: **anything that represents "a
mutation is in flight and needs to be finished correctly later" (a pending
confirmation, an idempotency key, a queued job) should be a database row with an
expiry from the moment it's designed**, even in a single-process prototype. The
question "what happens to this if the process restarts right now" is worth asking at
design time, because the answer is never used to justify the in-memory version once
you've written it down.

## 3. Basic web-app hygiene is cheaper to bake in than to migrate in later

CSRF protection, real password hashing, non-debug mode, secure cookies, and upload
MIME validation all landed together in a dedicated security pass —
`a97fedf`/`be38c2f`/`8f8bc31`/`43bc4a9` — roughly **a third of the way** through the
project's life (commit #109 of 346), not from the start. Two of these were
particularly expensive to retrofit rather than start with:

- **Password hashing started as raw SHA256** and required `8f8bc31` to add an
  auto-migration path (detect the old scheme at login, re-hash to werkzeug's pbkdf2)
  that a from-the-start choice of `werkzeug.security` would never have needed. Every
  password stored before that commit had to be silently upgraded on next login instead
  of just being right the first time.
- **CSRF tokens had to be retrofitted onto every existing POST form at once**
  (`be38c2f`, "Add CSRF tokens to all POST forms") — a mechanical, easy-to-miss-one
  sweep that `Flask-WTF` from the first form would have made a non-event.

None of this is exotic: password hashing library, CSRF middleware, and
`FLASK_DEBUG`/secure-cookie defaults are each a few lines to get right on day one, and
each became a dedicated audit-and-fix pass later because they weren't.

## 4. Decide the URL/blueprint namespace before templates accumulate `url_for()` calls

Introducing Flask blueprints later required renaming every endpoint reference
(`proposal_detail` → `proposals.proposal_detail`, etc.), which broke `url_for()` and
`redirect()` calls across the template layer all at once and needed its own cleanup
commit: `7f4bd46`, "Fix endpoint namespacing regressions and stabilize tests." Choosing
blueprint boundaries — even provisional ones — before the second or third template
exists costs nothing; doing it after fifteen templates already call `url_for()` with
flat endpoint names is a synchronized, error-prone, all-at-once rename with no partial-
completion state that's safe to ship.

## 5. A shared service/repository layer pays for itself the moment a second surface (REST, MCP, Telegram) needs the same business rule

`app/services/` and `app/repositories/` didn't exist until `6348820`
("refactor: introduce app package, services, and repositories") — well after the web
app, and appreciably before MCP and the Telegram assistant matured into their current
shape. By the time this session's Sprint 4/5 work went looking for it, REST and MCP had
independently reimplemented overlapping validation and query logic, and had quietly
drifted: REST silently coerced any truthy `basic_supplies` value (including the JSON
string `"false"`) where MCP validated it properly; MCP's `create_proposal` treated a
non-positive `created_by` as a different error class than REST and MCP's own
`create_poll`; REST's `GET /api/polls` had no pagination at all while MCP's
`list_polls` did. None of these were deliberate — they were the predictable result of
the same rule being written twice by two people (or two AI agents) months apart with no
shared function to call instead.

**The lesson generalizes past this specific refactor**: the moment you know a second
transport (a second API shape, a bot, a CLI, a second frontend) will eventually need to
do something a route already does, extract that something into a plain function with
its dependencies passed in as parameters — before the second surface exists, not after
it's already drifted. It costs one extra function definition up front and saves an
audit-driven parity-testing project later (this repo's Sprint 5 "Error-contract matrix
expansion" line item, essentially in full).

## 6. Decide up front whether this is one product surface or three

`app/mcp_server.py` and the Telegram assistant were both bolted onto an already-mature
web app rather than designed alongside it from the start. That ordering meant every
mutating capability (create a proposal, create a poll, cast a vote) had to be
re-validated a second and later a third time for each new surface, instead of the web
routes being thin callers of a service the other two surfaces would eventually share
(see item 5). If a bot or an API integration is even a plausible future requirement,
sketching the service boundary the *first* surface will call — not just the shape of
its own routes — avoids designing that first surface as something that later has to be
unwound.

## 7. Write the contract down before there's a contract to violate

`SPEC.md`, `APIDOC.md`, `IDEAS.md`, `STYLE.md`, `SPRINTS.md`, and `TESTING.md` didn't
exist as a set until roughly **60% of the way through** the project's current history
(commits #205–#225 of 346). Before that point, roughly 200 commits' worth of behavior,
API shape, and coding conventions existed only as "whatever the nearest similar code
happens to do" — exactly the condition that produces the kind of silent drift item 5
describes, and exactly the condition an AI coding agent (or a new human contributor)
has the hardest time detecting, because there's no written contract to check new work
against, only precedent to pattern-match from. A one-paragraph `SPEC.md` and a
half-page `STYLE.md` from commit 1 — even mostly wrong, even rewritten twenty times —
would have given every subsequent change something concrete to conform to or explicitly
revise, instead of nothing to conform to at all.

## 8. Scope a framework/frontend migration to one component before attempting the whole app

"Migrate to React" (`c1cde91`, PR #72) landed as one merge and needed an immediate
follow-up, "investigate React functionality issues" (`47a443c`, PR #74), four commits
later. What actually survives in the app today is a single hydrated component (the top
nav), with a fragile contract that the rest of the codebase now has to know about by
convention rather than by the type system: `_top_nav.html` carries an explicit comment
that "Inter-element whitespace is intentionally omitted so React can hydrate this exact
tree" — meaning a future edit to that template's formatting, made without knowing this,
silently breaks hydration with no error. Scoping the migration to exactly the
component that ended up surviving — one nav component, one hydration contract, tested
as a contract from the start (this exists now, per `TESTING.md`'s React hydration
coverage, but arrived after the fact) — would likely have reached the same end state
without the regression-and-rescope cycle in between.

## 9. Tests-as-a-baseline beat tests-as-a-regression-guard-after-the-fact

The first real test coverage (`04392e3`, "add pytest coverage for refactor
regressions") landed at commit #36 — meaning roughly the first ten percent of the
project's current history had no automated check on the core voting/proposal behavior
it was establishing. That ordering also shows up later in a different form: this
session spent real effort finally root-causing "4 pre-existing/environmental test
failures" that had been re-reported, unexamined, in nearly every progress note for the
length of an entire sprint — the actual causes (`python` vs. `sys.executable` in
subprocess tests, a Python 3.11/3.12 `_cffi_backend` mismatch) were mundane once
someone was forced to explain them, but "environmental" had been an acceptable label
for long enough that nobody had to. A test written alongside the feature it covers
(rather than a regression guard added during the next refactor) keeps both problems
from compounding: coverage starts where behavior starts, and a flaky-looking failure
gets a real diagnosis before it's had time to become "the four flaky tests everyone
ignores."

## 10. One commit, one concern — for the sake of whoever has to read this file later

Compare `ef39d0f` ("Add withdraw vote option for active proposals") to `00c6930`
("Add Telegram poll voting with inline keyboard, fix URLs, add CSRF tokens, update poll
page with 3 cards") or `86a9b86` ("Add purchase tracking, proposal filters, tags,
password change, and code cleanup"). Commits bundling three or four unrelated changes
are common in the first third of this project's history, and every one of them makes
`git bisect` and `git blame` less useful for exactly the question a retrospective like
this one has to answer — "when did this behavior start, and why" — forcing a read of
the whole commit body instead of a targeted look at one diff. This isn't a call for
ceremony; it's cheaper in the moment to make four small commits than one big one, and
it stays cheaper for as long as the repository exists.

## How to use this file

This is a retrospective, not a backlog — none of the above is a Sprint candidate by
itself (most of what it describes has since been fixed; see `SPRINTS.md`/`IDEAS.md` for
the current, forward-looking backlog). Its job is narrower: the next time this project
(or its next major surface) is tempted to skip one of these for speed, this is the
receipt for what skipping it cost last time.
