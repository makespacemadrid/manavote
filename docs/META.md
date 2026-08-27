# META — Retrospective: What ~300 Commits Ago Needed to Know

This project is 346 commits old as of this writing (`git log --oneline origin/main | wc -l`,
after unshallowing this session's clone to see the real, complete history back to the
first commit). "300 commits ago" lands around commit **#47** — chronologically, right
after the first withdraw-vote feature and before the first CSRF token, the first
password-hash migration, and the first `app/services/` module existed. This document
was first written from that vantage point; it has since been expanded from a full,
commit-by-commit read of the entire history (not a sample), so later sections also cover
things that only became visible from further out — how a second identity provider, a
second chat surface, and a second frontend framework each interacted with decisions made
long before they existed. Real, dated evidence throughout, not general advice.

Nearly all of this history — 315 of 346 commits — was authored by one person
(`web@luisriverag.com`) driving a coding agent through one small, single-purpose PR at a
time (branch names like `codex/fix-...`, `codex/add-...`); 29 more are this session's own
work. That matters for the second half of this document: this genuinely is what it looks
like to build a real, still-running app almost entirely through prompted AI-agent work,
which makes "what should the prompts have said" a question with a concrete, evidence-backed
answer rather than a hypothetical one.

This is not a criticism of the pace or judgment that got the project here — a
community-run budget-voting app iterating in public with real users is exactly the kind
of project where "ship it, fix it live" is often the right call. It's a note to whoever
starts the next project (or the next major surface on this one, or the next prompt to an
agent building either) with the unfair advantage of already knowing how this one turned
out.

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

## 7. A behavior spec without a process/convention doc will still fork and drift

Credit where due: `SPEC.md` existed from **commit #1** (73 lines, shipped alongside the
very first `app.py`) — a genuinely good early instinct, and one that held up better than
it might have. But a single loose file at the repo root, with no `docs/` structure and
no `STYLE.md` saying what belongs where, wasn't enough on its own: by commit #39 it had
already forked into a second, competing `SPECS.md` (199 lines) that needed a dedicated
commit (`91343cb`, "Consolidate SPEC.md and SPECS.md into single SPEC.md") to manually
reconcile a 328-line merge of the two. And the *process* docs that actually govern how
work gets done — `IDEAS.md` (a real backlog, commit #164), `STYLE.md` and `SPRINTS.md`
(conventions and tracking, both commit #223), `TESTING.md` (commit #225) — didn't arrive
until **47%–65% of the way through** the project's current history. That's exactly the
stretch where an accelerating stream of small, independent, single-purpose AI-agent PRs
most needed a shared reference to converge on, and instead had only "whatever the
nearest similar code happens to do" to pattern-match from — the same condition that
produces the silent REST/MCP drift item 5 describes. A `docs/` folder and a half-page
`STYLE.md` from commit 1 (even mostly wrong, even rewritten twenty times) would have
given every subsequent PR something to conform to or explicitly revise, and would have
made a second `SPECS.md` impossible to write by accident.

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

## 11. Specify a financial formula in one sentence before it goes into a chart

On a single day (2026-04-18), the budget/calendar chart's "Committed Budget" figure was
redefined **eight separate times** in eleven back-to-back commits — including a real
inverted-sign bug along the way (`b037b16`, "Fix budget balance calculation (income -
expense, not expense - income)"). Each commit changed the formula to fix how the chart
*looked* — `d7b540d` → `3ced080` → `e9f0569` → `07a4955`, each one a different definition
of "committed" — rather than starting from a one-sentence specification of what the
number means. A number members use to decide whether the community can afford something
was being defined by trial and error against a live graph. Writing the formula in
prose first (as a sentence any admin could check by hand against one example) is cheaper
than eight redefinitions and would have caught the sign bug before it shipped once,
let alone rendered on a page.

## 12. A feature that needs three "internal server error" hotfixes on launch day needed a smoke test before merge, not after

Polls shipped as PR #21, and the same day needed three consecutive follow-up PRs before
it stopped 500ing: "Fix polls page crashes and add missing Polls nav links" (#22-adjacent),
then "Fix internal server error in polls and admin" (#23), then "Fix internal server
error on /admin" (#24) — the underlying issue (`9687452`, "Avoid double app
initialization in startup wrapper") turned out to be a startup-ordering bug that any
request to the new page would have hit immediately. Unit tests of the pieces passed;
nobody had loaded the actual page before merging. One request against the happy path of
a new page, made before merge rather than by the first real user after it, would have
caught this in minutes instead of a day of live 500s.

## 13. A second identity provider will find every place the first one's assumptions were implicit

Telegram account linking was built assuming every member has a usable public username.
Months later, adding Keycloak/OIDC SSO login (PR #66) surfaced that assumption
immediately: `7046600` ("Fix Telegram linking without public username") and `f01e896`
("Add email-based account login and management") both exist because SSO-created members
don't necessarily have one. Nothing about the original Telegram-linking code was wrong
for the world it was built in — the assumption just was never written down, so there was
nothing to check the new login method against. Any feature built against "how members
currently authenticate" should state its assumptions about identity explicitly, because
the next auth method is exactly what will violate the ones left unstated.

## 14. Protocol-compliance surfaces need a real external client before "done," not just an internal reading of the spec

Four commits in immediate succession, right after MCP's introduction, were all the same
class of bug: `87102f3` ("Refine MCP proposal alias handling") → `c1621aa` ("Fix MCP
create_proposal dispatch name handling") → `186dcc5` ("Harden MCP batch error handling")
→ `c1e7614` ("Add MCP tool_name alias for tools/call compatibility"). Each one is a
mismatch between what the server implemented and what a real MCP client actually sent —
tool-name and dispatch-name shape assumptions that only surfaced once real traffic hit
the server. Implementing to a written protocol spec is necessary but not sufficient;
testing against one real client before calling the surface "done" would have caught this
whole class in one pass instead of four.

## 15. Chat-bot group/thread behavior has enough edge cases to spec before building, not discover one incident at a time

Four separate hardening PRs landed within about two hours on one day: "Harden Telegram
group address matching" → "Keep Telegram command replies in forum topics" → "Document
Telegram forum privacy requirement" → "Reliably route Telegram replies to forum topics"
(`1a00f80`, `6fc738f`, `220f2eb`, `fe8c192`). Each one added one more rule of "how should
the bot behave in a group or forum topic" that the previous fix hadn't covered yet —
addressing, thread routing, and privacy-mode requirements were each discovered live
rather than designed up front. This is the direct ancestor of Sprint 6 Goal 3's
`telegram_routing_decision` observability work earlier this session: the reason nobody
could easily answer "why didn't the bot respond in that group" is that the routing rules
themselves were assembled incident-by-incident rather than specified once.

## 16. Verify persistence against an actual container recreation, not just "the code writes to a path"

Backup file persistence broke across a container rebuild **twice**, months apart:
`0e22ae2` ("fix: mount backups volume in docker-compose to persist backup files"), then
later `aa26da4` ("fix: use bind mount for backups dir and ensure correct ownership in
Dockerfile") because the first fix didn't account for file ownership inside the
container. Both are the same underlying question — "does this file still exist and
remain readable after the container that wrote it is destroyed and recreated" — and
both were found by it actually happening rather than by testing for it. A single
deploy-rebuild-check cycle against the specific thing you're trying to persist would
have caught both issues in one pass.

## 17. Decide identity trust boundaries explicitly, at integration time — don't let an audit find them later

Whether an OIDC/SSO login is allowed to silently attach to an existing password-based
account by matching email address was never written down when Keycloak SSO was added.
It was only made explicit during this session's own retrospective work, when Sprint 5
flagged it as an open question and the human owner confirmed (`ed341a6`) that SSO is
the intended single source of identity truth and the email-matching behavior is
deliberate. The eventual answer isn't the problem — leaving a real trust-boundary
question implicit for months, discoverable only by an AI agent auditing the code cold,
is. Any second authentication method should ship with its trust decisions written down
next to the code that encodes them, not left for a future audit to reconstruct and ask
about.

## 18. When a display label changes, rename the underlying identifier too — or live with two vocabularies forever

The `over_budget` proposal status was renamed for *display* to "Pending Budget" within
two days of shipping (commits `9332544`→`652b8c4`, 2026-04-17/18) — but the status
value, the URL filter (`?filter=over_budget`), and every internal identifier were never
renamed to match. The result, still true in today's codebase: every user-facing surface
says "Pending Budget" and every line of code says `over_budget`. Renaming the identifier
at the same time as the label — even though it touches more files — costs a
find-and-replace once; leaving the split in place costs every future reader a small
"wait, which one do they mean" tax, forever.

## 19. Positive patterns this project's own history validates

Not everything here is a cautionary tale — two things this history shows genuinely
paying off are worth naming so they don't get lost in a list of regrets:

- **Small, single-purpose PRs got dramatically better over time.** Compare the bundled
  early commits in item 10 to the steady stream of one-concern-per-PR changes from
  roughly PR #4 onward (`a2cb397` and after) — most of that later stretch is one focused
  branch, one fix or one feature, merged and moved on. `git bisect` and `git blame`
  are far more useful for that half of the history than the first.
- **Group purchases (PR #71, `c9a300f`) shipped as one coherent unit**: schema
  (`app/db/migrations.py`, `app/db/schema.sql`), routes (620 lines), templates,
  translations, docs (`docs/SPEC.md`), and 256 lines of tests, all in the same PR — and,
  unlike polls or MCP, didn't need an immediate crash-fix cascade after merging. By the
  time this feature was built (commit #274 of 346), the project had visibly internalized
  several of the lessons above.

## How the build prompts should have been ordered

Since this app really was built almost entirely by prompting a coding agent, PR by PR
(see the authorship note above), the findings above aren't abstract lessons — they're a
direct trace of what happens when prompts are reactive ("fix this bug," "add this
feature") instead of sequenced. Below is the phase order that this history itself argues
for: each phase names the prompt that should have come before any code, and which
finding above it would have prevented.

**Phase 0 — Domain spec, before any code (prevents findings 7, 11, 18).** One prompt,
answered in prose before the first route exists: name every entity and its states using
the exact identifiers the code will use (not a display label picked later); write the
one-sentence definition of every money calculation the app will show (balance, committed
budget, thresholds) in words a non-programmer could verify by hand against one example;
and start `docs/SPEC.md` and `docs/STYLE.md` as real files in the first commit, not
placeholders — a spec that's mostly wrong on day one is still a single source of truth
to correct, instead of the second competing file this project actually produced.

**Phase 1 — Runtime and surface commitments, before the second feature (prevents
findings 2, 5, 6).** One prompt, answered before writing the second route: will this
ever be more than a single-process web app (multiple workers, restarts, a redeploy
pipeline)? Will anything other than a browser ever need to do the things this app does
(a bot, a public API, a second frontend)? If either answer is "maybe," design accordingly
now: a thin service layer beneath routes from the first mutating endpoint, and durable
(database-backed, not in-memory) storage for anything that represents "this operation
isn't finished yet." Both are nearly free before a second surface exists and expensive
retrofits (this project's Sprint 4/5 A2 work, and the shared-SQLite migration in finding
2) once it does.

**Phase 2 — Security and conventions baseline, before the first form ships (prevents
findings 3, 4, 10).** One prompt, applied once and then never revisited per-feature:
CSRF protection, a real password-hashing library, secure-cookie policy *with* an
explicit local-HTTP-dev escape hatch (finding 3's later fix, `61c4926`, exists because
this wasn't decided up front), non-debug-by-default, upload validation, blueprint/URL
namespacing decided even provisionally, and a one-line commit-message rule ("one
concern per commit"). None of this is feature work, which is exactly why it's cheap now
and expensive as a dedicated "AUDIT fixes" pass later.

**Phase 3 — Core domain, one full vertical slice at a time, spec → tests → code → docs,
in that order (prevents findings 1, 9, 12).** For each feature (proposals, voting,
thresholds, comments, budget ledger): write the acceptance behavior first, including
edge cases, as a checklist the agent confirms against before calling it done; write
tests against that checklist before or alongside the implementation, not after the next
refactor needs them; and require one smoke-test pass of the actual new page's happy path
before merge, not just unit tests of the pieces (finding 12's polls launch-day crashes
were exactly this gap). Establish the shared button/component vocabulary (finding 1)
as part of the *first* slice, since every later slice will reach for it or bypass it.

**Phase 4 — Each new external surface, spec'd against the first before it's built
(prevents findings 5, 14, 15).** Before writing REST, MCP, or a chat bot integration:
write down the contract the new surface must match (request/response shape, error
codes, protocol quirks) against a real reference client or spec, not an internal
reading of one; and for anything with its own addressing/routing rules (a chat bot's
group-chat and thread behavior, in this project's case), write those rules down as a
checklist before implementing the webhook handler, not as a series of "harden X"
follow-up PRs discovered one incident at a time.

**Phase 5 — Each new identity/auth method, audited against the current one's
assumptions before merge (prevents findings 13, 17).** Before adding a second login
method: list every assumption the current auth system makes that isn't written down
anywhere (must every user have X, is Y globally unique, does matching Z silently link
accounts) and check the new method against each one explicitly. Answer the trust
questions this raises (like "does an SSO login attach to an existing account by email
match") as a documented decision made *now*, not a question an audit asks later.

**Phase 6 — Any framework/frontend change, scoped to the smallest provable unit
(prevents finding 8).** Prompt for the migration of exactly one component first, with
its contract (e.g. a hydration boundary) written down and tested as a named invariant —
not a comment in the template that only the person who wrote it will remember. Prove
the Docker/build story for that one component before scoping wider, since the fastest
follow-up fix this project needed after any framework change was a broken build.

## How to use this file

This is a retrospective, not a backlog — none of the findings above are Sprint
candidates by themselves (most of what they describe has since been fixed; see
`SPRINTS.md`/`IDEAS.md` for the current, forward-looking backlog). Their job is
narrower: the next time this project (or its next major surface) is tempted to skip one
of these for speed, this is the receipt for what skipping it cost last time. The prompt
sequencing above is the same evidence turned forward instead of backward — for whoever
next opens a blank prompt to build something like this, in this project or the next
one, and could use the six phases instead of rediscovering them.
