# META — Retrospective: What I wish I'd known ~300 Commits Ago

> **TL;DR:** Almost every regression documented below follows one shape — a decision
> made implicitly held up fine until something *second* arrived (a second surface, a
> second auth method, a second commit touching the same feature) and broke it, live,
> in front of users. See "The pattern behind these findings" for the mechanism and a
> 30-second theme map of all 22 findings; "How the build prompts should have been
> ordered" for a literal, bottom-up, 14-layer sequence that would regenerate *this
> app's* current functionality; or "Generalized learnings, for projects that aren't
> this one" for the tech-agnostic version and a single starter prompt for *any* new
> project.

This project is 348 commits old as of this writing (`git log --oneline origin/main | wc -l`,
after unshallowing this session's clone to see the real, complete history back to the
first commit). "300 commits ago" lands around commit **#47** — chronologically, right
after the first withdraw-vote feature and before the first CSRF token, the first
password-hash migration, and the first `app/services/` module existed. This document
was first written from that vantage point; it has since been expanded from a full,
commit-by-commit read of the entire history (not a sample), so later sections also cover
things that only became visible from further out — how a second identity provider, a
second chat surface, and a second frontend framework each interacted with decisions made
long before they existed. Real, dated evidence throughout, not general advice.

Nearly all of this history — 317 of 348 commits — was authored by one person
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

## The pattern behind these findings

Read individually, the findings below look like unrelated bugs across unrelated
features. Read together, all but two of them (1 and 22) share one mechanism: a decision
was made implicitly, worked fine in the world that existed when it was made, and broke
the moment a **second thing** arrived that the original decision never accounted for —
a second surface calling the same logic (findings 5, 6, 14), a second identity provider
or auth method (13, 17), a second commit or second episode touching the same feature
(1, 11, 18, 19, 21), a second container recreation (16), a second (or tenth) template
depending on a read path nobody proved yet (20), or simply a second contributor or agent
with no written convention to read (7, 9, 10). Almost none of the individual fixes were
hard once found — most are a few lines. The cost was never in the decision itself; it
was in the gap between *when the decision was made* and *when it was written down*, and
the "second thing" reliably arrived somewhere inside that gap. The prompt sequence at
the end of this document exists to close that gap before it opens, not to make better
decisions — most of the original decisions were fine for the world they were made in.

Adding up just the findings below with an explicit, named commit count (1, 3, 4, 7, 8,
11, 12, 13, 14, 15, 16, 19, 20, 21 — the eight findings without one, like "REST and MCP
drifted" or "tests arrived late," represent real cost too, just not one expressible as
a commit tally) comes to **at least 48 commits** spent specifically on rework whose root
cause predates it, out of 348 total — call it one commit in seven. That's a lower bound,
not an estimate of total waste: it only counts commits this document cites by hash, not
every smaller ripple those root causes caused elsewhere, and finding 19's four commits
are deliberately counted separately from finding 11's eleven so nothing is counted
twice.

A quick map of what's below, grouped by theme rather than commit order:

| Theme | Findings |
| --- | --- |
| Architecture & where state lives | 2, 5, 6, 20 |
| Security & baseline hygiene | 3, 4 |
| Process & documentation | 7, 9, 10, 21 |
| Money and domain-meaning | 11, 18, 19 |
| External integrations (bots, APIs, auth, infra) | 13, 14, 15, 16, 17 |
| UI/UX consistency & scope | 1, 8 |
| What actually worked | 22 |

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
project's life (commit #109 of 348), not from the start. Two of these were
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
unwound. (This specific gap — MCP called in-process with the server's own credentials
rather than through a real application boundary — was finally closed in `bf24b6c`,
"Complete Sprint 8 MCP application boundary," landing the day after this document was
first written and roughly 200 commits after the surface it fixes was introduced.)

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

## 19. Numeric/unit bugs in money and thresholds recurred across a month, not just one bad day

Finding 11 covers one day's thrash on the budget chart. Pulling every commit whose
message starts with "Fix" and touches a number a member sees shows that same *class*
of bug recurring in at least three more episodes that finding 11 doesn't cover: an
early one, five weeks before the budget chart existed at all (`beeaf49`, "Fix vote
threshold validation for over-budget proposals," 2026-03-31); an immediate follow-up
two days after finding 11's thrash supposedly settled it (`d95eb8a`, "Fix committed
chart pending calculation timing," 2026-04-20); and, twelve days after that, a
different unit-confusion bug in the same threshold system finding 11 doesn't touch —
vote requirements displayed as absolute counts when they were meant to be percentages
(`dba0747` and `0d94642`, 2026-04-30). Four separate episodes, five weeks, two
different features (vote thresholds and the budget chart), one shared root cause: no
number the app shows a member had a written definition to check the code against.
**Every number this app has ever displayed to a member needed at least one correctness
fix after shipping.** A one-line worked example per formula or threshold, asserted in
a test, is cheaper than any single one of these five fixes and would have caught all of
them together.

## 20. Cross-cutting per-request state needs one prototype before the tenth template reads it

Adding a language switcher took one feature commit (`4a368d8`) and then four
consecutive "Fix language switching" commits before it worked reliably: session access
from inside a template filter (`59cad0b`), the selector markup itself (`3bbbffd`), the
context-processor-vs-Jinja-filter split for reading the current language (`8c30960`),
and Jinja's own template cache silently serving a page in the wrong language after a
switch (`cedf2ee`) — plus, the same day the feature launched, a Docker build that
didn't copy the new `translations.py` module at all (`b04b157`). Each fix addressed a
different layer of "how does a per-request preference reach every template," found
only after dozens of templates already called the translation filter. This isn't
i18n-specific: **any cross-cutting per-request state (language, theme, feature flag,
tenant) needs its full read path — session or cookie, through a context processor or
global, into the template, verified against the actual template-caching behavior in
use — proven against one template before a second template starts depending on it.**
Unwinding a wrong read path once ten templates use it means touching all ten, not just
the mechanism.

## 21. A convention stated only in a commit message isn't a convention yet

`ddd8e2c` ("Use Title Case for filter buttons, lowercase for status tags") documented a
real UI rule — and needed a same-morning follow-up, `e504603` ("Fix filter Title Case
vs status lowercase correctly"), because the first attempt didn't actually apply it
everywhere. A rule that exists only as commit-message prose (or a comment three files
from where it's enforced) has no way to be checked except a human noticing a violation
by eye — which is exactly what failed the first time here. This is the same shape as
finding 18's `over_budget`/"Pending Budget" split and finding 7's missing `STYLE.md`,
but the fix is more specific and worth naming on its own: a convention like this
belongs in a snapshot test, a lint rule, or at minimum one line in `STYLE.md` that a
reviewer — human or agent — is expected to check a PR against, not just a well-intentioned
sentence in a commit that already merged.

## 22. Positive patterns this project's own history validates

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
  time this feature was built (commit #274 of 348), the project had visibly internalized
  several of the lessons above.
- **Finding 7's thesis got a live re-run while this document was being written.**
  `IDEAS.md`'s "Member feedback / bug reports / suggestions" entry specified a
  `feedback_service.py` shape and flagged one open design question by name: mutating
  MCP tools were all admin-only so far, so a member-writable `create_feedback` tool
  would need a new tool-access category, suggested as `MEMBER_WRITABLE_TOOLS`, and it
  was unclear whether it should require the existing `/confirm` flow. Commit `bf24b6c`
  ("Complete Sprint 8 MCP application boundary"), from a *different* agent on a
  different branch, implemented exactly that — the same category name, exposed
  alongside but separate from the existing admin-only `MUTATING_TOOLS`, with feedback
  submission correctly left out of the confirmation flow. A spec doesn't have to be
  perfect to work; it has to exist somewhere the next PR (or the next agent) will
  actually read it, which is the entire argument for writing each layer's prompt down
  below rather than reconstructing it from memory each time.

## How the build prompts should have been ordered

Since this app really was built almost entirely by prompting a coding agent, PR by PR
(see the authorship note above), the findings above aren't abstract lessons — they're a
direct trace of what happens when prompts are reactive ("fix this bug," "add this
feature") instead of sequenced. What follows is not a generic template: it's the
literal, ordered, bottom-up prompt sequence that would generate *this specific app's
current functionality*, using the app's actual entities, columns, thresholds, routes,
and tool names as they exist in the codebase today — checked against `docs/SPEC.md`,
`app/db/schema.sql`, `app/db/migrations.py`, and `app/mcp_server.py` at time of writing,
not remembered or approximated. Each layer depends only on layers already built, with
one deliberate, explicitly-marked exception (Layer 7 stubs a Telegram announcement it
can't finish until Layer 9 exists, rather than pretending the dependency isn't there) —
a stub with a named forward dependency is honest bottom-up engineering; a silent one
is exactly the kind of unwritten assumption this whole document is about. Each layer
names the findings above it would have prevented and gives one literal, pasteable
prompt.

| Layer | Builds | Depends on | Findings prevented |
| --- | --- | --- | --- |
| 0 | Skeleton, security baseline, shared UI/confirm-modal system | nothing | 3, 4, 7, 10, 21 |
| 1 | Members, settings, auth (password-only) | 0 | 13, 17 (assumptions named early) |
| 2 | Proposals, votes, budget ledger, thresholds | 1 | 11, 18, 19 |
| 3 | Comments, admin panel v1 | 2 | 1, 3, 21 |
| 4 | Proposals UX, budget chart | 2, 3 | 11, 19 |
| 5 | i18n (EN/ES) | 3, 4 | 20 |
| 6 | Polls | 1, 2, 3 | 1, 12 |
| 7 | Group purchases | 1, 3 | 9, 22 (positive pattern) |
| 8 | Service/repository layer, REST API, MCP server + authz boundary | 2, 6, 7 | 5, 6, 14 |
| 9 | Telegram (commands, webhook, assistant, confirm flow) | 8 | 2, 6, 13, 15 |
| 10 | OIDC/Keycloak SSO | 1, 9 | 13, 17 |
| 11 | React/Vite nav hydration | 0 | 8 |
| 12 | Member feedback + structured observability | 8 | 7 (live-validated), 9 |
| 13 | Docker/persistence, backups, startup orchestration | everything | 16 |

### Layer 0 — Skeleton, security baseline, and a shared UI/confirm-modal system

Nothing here is feature work — it exists so every later layer has something to build
on instead of something to retrofit onto.

> **Prompt:** "Set up a Flask app with this structure: `app/web/app_setup.py` builds
> the Flask app object (config from environment, logging, `Flask-WTF` `CSRFProtect`,
> `Flask-Limiter`); `app/__init__.py` exposes `create_app()`; `app/db/connection.py`
> gives a `get_db()` SQLite connection helper; `app/db/schema.sql` is a documentary,
> non-executed reference of the current schema; `app/db/migrations.py` has a single
> `run_migrations(cursor)` entry point using an `add_column_if_missing(cursor,
> table_name, ddl)` helper for every schema change from now on, plus fresh `CREATE
> TABLE IF NOT EXISTS` statements for new installs. Decide the blueprint namespace now,
> even though only auth exists yet: `auth`, `api`, `proposals`, `polls`, `admin`,
> `group_purchases`, `telegram` — every `url_for()` from the first template uses the
> namespaced form (`auth.login`, not `login`). Security baseline, as one commit: CSRF
> on every form; hash passwords with `werkzeug.security`; `SECRET_KEY` must be a
> non-default value when `FLASK_ENV=production` (fail startup otherwise); cookies are
> secure via `FLASK_SECURE_COOKIES` (default `false`, `true` when `FLASK_ENV=production`)
> so local HTTP development isn't broken by default; debug mode off unless
> `FLASK_DEBUG` is explicitly set; rate-limit login to `5 per minute`. Start
> `docs/SPEC.md` (behavior contract) and `docs/STYLE.md` (conventions) as real files,
> even mostly empty. In `STYLE.md`, and applied immediately in the base template and
> CSS: a dark theme (`body` background `#111111`, text `#eee`), a `.card` container
> class, a `.btn` primary-action class, a `.vote-btn` class with `.approve` (cyan
> `#00d9ff`) and `.reject` (red `#e94560`) variants, and `.status`/`.status-<name>`
> badge classes — every later feature must use these, never a one-off inline
> `style=`. Build one shared, reusable confirm-action modal now (a hidden `<div>`
> toggled by JS, `role=\"dialog\"`, `aria-modal=\"true\"`, focus trap, Escape-to-close,
> a `confirmDangerAction(form, message)` JS helper that shows the modal and submits
> the given form on confirm) — every destructive action in every later layer must call
> this, never a native `confirm()`. One-concern-per-commit is the rule from commit one,
> enforced by you telling me explicitly if a change I ask for bundles more than one
> concern, rather than silently doing both."

### Layer 1 — Members, settings, and password auth

> **Prompt:** "Add a `members` table: `id` (PK), `username` (unique, not null),
> `password_hash` (not null), `is_admin` (int, default 0), `created_at` (default
> `CURRENT_TIMESTAMP`). Even though nothing but password login exists yet, also add
> `telegram_username`, `telegram_user_id`, `last_linked_at`, `last_unlinked_at`,
> `oidc_sub` (unique), `email`, `display_name` — all nullable — because a Telegram
> integration and an SSO login are both planned, and every assumption password-only
> auth makes (must a member have a username? is email unique? can two identities
> merge?) needs to be checkable against these columns later without a migration
> fire-drill. Add a generic `settings` table (`key` PK, `value`), seeded with
> `registration_enabled = true`. Build registration (togglable via
> `registration_enabled`), login accepting either `username` or `email`
> case-insensitively (matching by username first), a 30-day session
> (`PERMANENT_SESSION_LIFETIME`), and bootstrap the first admin from an
> `ADMIN_BOOTSTRAP_PASSWORD` environment variable — missing it is a hard startup error
> when `FLASK_ENV=production`, and an insecure default with a loud warning otherwise.
> Write down, in `docs/SPEC.md`, the exact list of auth assumptions this layer makes
> (one username per member, one password scheme, no email uniqueness enforced yet) so
> a later SSO layer has something concrete to check itself against."

### Layer 2 — Proposals, votes, and the budget ledger

The formulas are specified in prose, with the actual numbers, before any code —
finding 19 exists because this project didn't do that until five separate numeric bugs
forced it to, over five weeks.

> **Prompt:** "Add three tables: `proposals` (`id`, `title`, `description`, `amount`
> real not null, `url`, `image_filename`, `created_by` not null, `created_at`,
> `status` default `'active'`, `processed_at`, `over_budget_at`, `purchased_at`,
> `basic_supplies` int default 0); `votes` (`id`, `proposal_id`, `member_id`, `vote`,
> `created_at`, unique on `(proposal_id, member_id)`); `activity_log` (`id`, `amount`
> real not null, `description`, `created_by`, `created_at`, `proposal_id` nullable —
> the running budget is always computed as `SUM(amount)` over this table, never a
> stored balance). Before writing any voting logic, write these rules in
> `docs/SPEC.md` exactly, then write one test asserting each against a worked example
> with real numbers before implementing it: (1) `min_backers = max(1, int(member_count
> * threshold_percent / 100))`; (2) threshold selection is `basic_supplies == 1` →
> setting `threshold_basic` (seed the setting at `5`, i.e. 5% of members), else
> `amount > 50` → `threshold_over50` (seed at `20`), else `threshold_default` (seed at
> `10`) — note for whoever maintains `docs/SPEC.md`: an earlier version of this spec
> also wrote '(default: 2/8/4)' next to this rule, which contradicts the actual seeded
> settings values of 5/20/10 checked directly against the code — resolve which is
> correct before copying either; (3) a proposal is approvable when both
> `net_votes = in_favor - against >= min_backers` AND `amount <= current_budget`; (4)
> proposal status starts `active`; becomes `approved` (with a negative `activity_log`
> entry and `processed_at` set) when threshold is met and budget allows; becomes
> `over_budget` (with `over_budget_at` set) when threshold is met but budget doesn't
> allow, and is automatically reconsidered for approval whenever budget increases;
> `rejected` is a valid status value reachable through the data model even if no
> current code path assigns it — decide explicitly whether that's intentional or a gap
> before building the next layer on top of it; admin can undo an `approved` proposal
> back to `active`, restoring the budget and clearing `processed_at`/`purchased_at`;
> (5) a proposal flagged `basic_supplies` whose `amount` exceeds €20 automatically has
> the flag cleared and an explanatory comment inserted — write this as its own test
> with `amount = 20.01` as the boundary case. Build proposal CRUD and the vote
> endpoint only after every one of these tests passes against hand-picked numbers."

### Layer 3 — Comments and the first admin panel

> **Prompt:** "Add a `comments` table (`id`, `proposal_id`, `member_id`, `content` not
> null, `created_at`). Build an admin panel with member management (add/remove,
> toggle `is_admin`, change any member's password) and manual budget entries
> (arbitrary description/amount into `activity_log`, plus a one-click 'Monthly
> top-up' action for a configurable amount). Every destructive action here (removing
> a member, deleting a comment, undoing a proposal's approval) must go through the
> shared confirm modal from Layer 0 — do not reach for a native `confirm()` even
> though it would be faster; that shortcut is exactly what this project did, and it
> took a dedicated pass much later to unwind."

### Layer 4 — Proposals UX and the budget chart

Same discipline as Layer 2: the chart's formulas are specified in prose, checked by
hand against one example, before any Chart.js code — finding 19's whole cluster
was this exact mistake, made three separate times across a month.

> **Prompt:** "On the proposals list: status/category filter chips (all filters using
> the shared component from Layer 0, including a visibly active state for every
> filter including 'All' — a filter with no visual selected-state is a real, subtle
> bug), tags for `basic_supplies` proposals and for `amount > 50`, inline quick-voting
> showing 'N votes out of M required.' Self-host Chart.js under `static/vendor/` —
> don't load it from a CDN at render time. Before writing the chart: write down, in
> `docs/SPEC.md`, one sentence per series with a worked numeric example: 'Budget
> Balance' is the running `SUM(activity_log.amount)`; 'Pending' accumulates the amount
> of every proposal currently `over_budget` (tracked via `over_budget_at`) and
> decreases when one of those gets approved; 'Committed' is `Budget Balance − Pending`
> (a negative Committed means pending commitments exceed available budget — write
> that sentence down explicitly, it is not obvious from the formula alone). Write one
> test per series against a small fabricated `activity_log`/proposals fixture before
> writing the Chart.js configuration that renders them."

### Layer 5 — i18n (English/Spanish)

Prototyped against one template before it's wired into the rest of the app — finding
20's four consecutive "fix language switching" commits happened because this project
wired the translation filter into a dozen templates before proving the read path.

> **Prompt:** "Add a language switcher (English/Spanish) as a `translations.py`
> dictionary and a Jinja filter. Before adding it to a second template: prove the full
> read path against exactly one template — where the chosen language is stored
> (session), how a Jinja filter or context processor reads it mid-request, and
> whether Flask/Jinja's template caching could serve a previously-rendered page in the
> wrong language after a switch (it can, by default — decide how this is disabled or
> worked around explicitly, in writing, before continuing). Only once that one
> template round-trips correctly (switch language, reload, see it took effect) should
> the same filter be added to every other template. Update the Docker build's file
> list in the same commit that adds `translations.py`, and add a build-smoke-test step
> that would have caught it being missing."

### Layer 6 — Polls

> **Prompt:** "Add `polls` (`id`, `question`, `options_json`, `created_by`,
> `created_at`, `status` default `'open'`, `closes_at`) and `poll_votes` (`id`,
> `poll_id`, `member_id`, `option_index`, `created_at`, unique on `(poll_id,
> member_id)` — latest vote replaces the prior one). Enforce identically, in one
> shared validation function reused by every entry point that will ever create a
> poll: question 5–200 characters, 2–12 options, each option ≤120 characters. Give
> each poll option's result bar a distinct color, not a repeated gradient. Store
> `poll.counts` as a list indexed by `option_index`, not a dict keyed by some other
> value — decide the exact data structure and write one test indexing into it before
> writing the template that renders vote counts. Before merging, load the actual new
> `/polls` page end-to-end once as a smoke test, including its interaction with the
> admin panel's poll-management tab — this project's polls launch needed three
> separate 'internal server error' hotfixes on launch day because nobody did this
> before merging, and the actual bug was a startup-ordering issue any real page load
> would have hit immediately."

### Layer 7 — Group purchases

This is the one feature this project's own history got right on the first pass —
build this layer the same way: schema, routes, templates, and tests together, in one
PR, not staged across several.

> **Prompt:** "Add five tables in one migration: `group_purchases` (`id`, `title`,
> `description`, `created_by`, `created_at`, `status` default `'open'` — lifecycle
> `open` → `ordered` → `received` — `deadline`, `url`, `image_filename`,
> `payment_method`); `group_purchase_components` (`id`, `group_purchase_id`, `name`,
> `position` default 0, `unit_price` real default 0); `group_purchase_quantities`
> (`component_id`, `member_id`, `quantity`, `updated_at`, PK on
> `(component_id, member_id)`); `group_purchase_payments`
> (`group_purchase_id`, `member_id`, `received_at`, PK on both); `group_purchase_shared_costs`
> (`id`, `group_purchase_id`, `label`, `amount`, `position`). Any member can create a
> shared purchase with up to 30 option rows, a deadline, product URL, image, and
> payment instructions. Shared costs (shipping, taxes) split proportionally: each
> participant pays the same percentage of shared costs as their percentage of the
> total selected-product value — write that formula down with a worked example before
> implementing it. Quantities and prices are editable only while `open`; the creator
> advances the lifecycle and can mark individual participants' payments as received.
> Announce creation, marking-ordered, and marking-received to the configured Telegram
> group/thread (build this against Layer 9's Telegram client once that layer exists;
> stub it before then). Ship the schema, the routes, the templates, the translations,
> and the tests together, in this one PR — do not split them across multiple merges."

### Layer 8 — Service/repository layer, REST API, and the MCP server

The service/repository extraction happens *before* REST and MCP are written, not
after they've already drifted from each other — this is finding 5 and 6's whole
argument, and finding 14's MCP-specific protocol-compliance lesson applies to the
tool definitions built here.

> **Prompt:** "Before writing REST or MCP: extract the business logic proposals,
> polls, votes, and group purchases already use into `app/services/*.py` and
> `app/repositories/*.py` — plain functions/classes taking `get_db`,
> `get_setting_value`, and a logger as explicit parameters, never reaching for Flask
> globals, so the same function can be called from a web route, a REST handler, and a
> Flask-independent MCP process. Build the REST API (`api_routes.py`, admin-key
> authenticated via `X-Admin-Key`, CSRF-exempt, `503` if the key isn't configured):
> `POST /api/register`, `POST/GET/PUT/PATCH /api/proposals[/<id>]` (list supports
> `status`, `age=recent|old` around a 30-day boundary, `limit`/`offset`),
> `GET/POST /api/polls`, `GET /api/members/telegram`, `GET /api/members/statistics`
> (opt-in `include_email`), `GET/PUT/PATCH /api/settings/voting` — every list endpoint
> uses one shared pagination-validation function, not five copies of the same
> try/except. Build `app/mcp_server.py` as a standalone module that must never import
> Flask (it runs as its own process over HTTP or TCP, controlled by
> `MCP_SERVER_ENABLED`/`MCP_SERVER_TRANSPORT`), exposing JSON-RPC 2.0 tools:
> read tools `list_proposals`, `list_polls`, `list_user_statistics`,
> `list_group_purchases`, `current_budget`, `list_member_telegram_links`,
> `get_voting_settings`; write tools `create_member`, `create_proposal`, `create_poll`,
> `update_voting_settings`. Every tool that exists in both REST and MCP calls the
> exact same Layer-8 service function — write one parity test per shared operation
> that fails if REST and MCP ever return different results for the same input, before
> either is considered done. Test the MCP surface against one real external MCP
> client, not just your own reading of the JSON-RPC spec, before calling it finished —
> tool-name and request-shape mismatches only show up against real traffic. Build a
> transport-neutral authorization boundary now, not later: an `Actor` (role +
> optional `member_id`) and an `execute_tool(executor, tool_name, arguments, actor)`
> function that checks a per-tool policy (`admin_read`, `member_write`,
> `confirmed_admin_write`) before invoking anything, used by both the in-process
> caller (Layer 9's Telegram assistant) and any external MCP client — do not let the
> Telegram integration call the tool executor directly with the server's own
> credentials and no policy check, even though that's the fastest way to wire it up
> first."

### Layer 9 — Telegram: commands, webhook, and the natural-language assistant

Persistent state from the first line, not an in-memory dict retrofitted later
(finding 2); group/forum-topic addressing rules written down before the webhook
handler exists, not discovered one incident at a time (finding 15); role-based tool
access designed in from the start using Layer 8's authorization boundary, not
Sprint-8'd in after the fact (finding 6).

> **Prompt:** "Add three SQLite-backed tables before writing any Telegram logic —
> `telegram_update_dedup` (`update_id` PK, `accepted_at`), `telegram_pending_actions`
> (`chat_id`, `telegram_user_id`, `tool_name`, `arguments_json`, `actor_member_id`,
> `created_at`, `schema_fingerprint`, `arguments_digest`, PK on
> `(chat_id, telegram_user_id)`), `telegram_conversation_history` (bounded to the
> last 12 turns per chat/user) — all shared across application workers and surviving
> restarts, because an in-memory dict here is a rewrite waiting to happen, not a
> shortcut. Build the webhook (`POST /telegram/webhook/<secret>`, secret checked
> against `TELEGRAM_WEBHOOK_SECRET`) handling deterministic commands `/vote`,
> `/pvote`, `/link <app_username> <app_password>`, `/help`, `/reset`, and poll inline
> callbacks `showvote:<poll_id>` / `pollvote:<poll_id>:<option_index>`. Before writing
> the natural-language addressing logic, write down as a checklist, not discovered
> live: a message qualifies in a private chat always; in a group only when it
> `@mentions` the configured `TELEGRAM_BOT_USERNAME`, replies to the bot's own
> message, or is posted in the admin-configured forum topic
> (`TELEGRAM_CHAT_ID`+`TELEGRAM_THREAD_ID`, treated as an always-on conversation);
> warn at startup if a group/thread is configured without `TELEGRAM_BOT_USERNAME`,
> since that makes the mention-matching overly permissive. Vote-to-member mapping
> prefers `telegram_user_id`, falls back to username matching, and — when
> `telegram_require_linked_vote=true` — rejects unlinked voters outright rather than
> falling back. Build the natural-language assistant against Layer 8's `execute_tool`
> boundary: members get `member_read`-policy tools plus (via the `member_write`
> policy) anything explicitly safe for a member to write about themselves;
> administrators additionally get `admin_read` and, behind a `/confirm` step,
> `confirmed_admin_write` tools. For every `confirmed_admin_write` tool call:
> propose it as a pending action with a fingerprint of its current input schema and a
> digest of its arguments; require `/confirm` within `TELEGRAM_CONFIRM_TTL_SECONDS`,
> re-verifying both the fingerprint and digest at confirm time so a stale or tampered
> pending action is rejected rather than executed; log a reason-coded audit event at
> every step (`proposed`, `confirmed`, `completed`, `failed`, `cancelled`, `expired`,
> `rejected`) from the first version of this flow, not added in retrospect."

### Layer 10 — Keycloak/OIDC SSO

Every assumption Layer 1's password-only auth made gets checked explicitly against
this new login path, and the trust decision it raises gets written down now, not
reconstructed by an audit later (findings 13 and 17).

> **Prompt:** "Before implementing Keycloak/OIDC SSO login: list every assumption
> Layer 1's auth made that isn't written down anywhere — must every member have a
> `telegram_username` set through `/link` specifically, is `email` guaranteed unique,
> can two identities be merged automatically — and check SSO against each one
> explicitly. Implement the Authorization Code flow
> (`GET /auth/login/keycloak` → `GET /auth/callback/keycloak`, rate-limited
> `10 per minute`), requiring the ID token's `groups` claim to contain
> `OIDC_REQUIRED_GROUP` (default `members-active`) and syncing an `admins` group
> membership to `is_admin` on every login, including removal. For member
> provisioning: resolve by `oidc_sub` first; if none exists and the claims carry an
> `email`, decide explicitly — and write the decision into `docs/SPEC.md`, not just
> into the code — whether finding an existing password-login member with a matching
> email should silently attach the SSO identity to that account, or require an
> explicit confirmation step. Whichever you choose, that's the trust boundary; don't
> leave it implicit for a future audit to discover and ask about."

### Layer 11 — React/Vite navigation hydration

Scoped to exactly the one component that should survive contact with reality
(finding 8) — not the whole app.

> **Prompt:** "Migrate exactly the top navigation component to React, hydrated onto
> server-rendered markup — not a wider rewrite. Set up `frontend/src/` with a Vite
> build (`vite build` writing fixed-name `app.js`/`style.css` into `static/react/`,
> matching what the base template already references) and `main.jsx`/`Nav.jsx`.
> Write down the hydration contract explicitly, as a comment and as a test, not just
> as tribal knowledge: the server-rendered nav markup and the client-hydrated markup
> must match exactly, including inter-element whitespace, or React's hydration
> recovery will cause a visible flash/layout shift. Verify the Docker build succeeds
> with this component migrated before proposing anything else move to React."

### Layer 12 — Member feedback and structured observability

By the time this layer is built, Layer 8's authorization boundary already exists — so
a member-writable capability like this is a natural extension of it, not a new
precedent to invent under time pressure.

> **Prompt:** "Add a `feedback` table (`id`, `member_id` not null, `source`
> constrained to `web`/`telegram`/`api`, `category` constrained to
> `bug`/`suggestion`/`other`, `message`, `status` default `'new'`, `created_at`,
> `resolved_at`, `resolved_by`). Build `submit_feedback`/`list_feedback`/
> `update_feedback_status` as Layer-8-style service functions, logging
> `event=feedback_submitted source=... category=...` on submission. Expose
> `POST /api/feedback` and `GET /api/feedback` (admin-only, paginated) and a
> `create_feedback` MCP tool under the `member_write` policy from Layer 8 — any
> linked member can submit feedback about themselves, without going through the
> `/confirm` flow that `confirmed_admin_write` tools require, since this is low-stakes
> and easily correctable. Apply the same reason-coded, `event=... source=...
> reason_code=...` logging convention to every other rejection path this app has
> (blocked votes by channel policy, blocked votes by link requirement) rather than
> treating this feedback feature's logging as a one-off."

### Layer 13 — Docker, backups, and startup orchestration

Verified against an actual container recreation, not just "the code writes to a
path" (finding 16).

> **Prompt:** "Write a multi-stage Dockerfile (Node stage builds the Vite frontend,
> Python stage serves Flask on `0.0.0.0:45000`) and a `docker-compose.yml` using named
> volumes for `app.db` (`APP_DB_PATH=/data/app.db`) and `static/uploads` — not host
> bind mounts, and with explicit ownership so the app user can write to both after a
> rebuild. Prove this by actually rebuilding the container and confirming a file
> written before the rebuild is still present and readable after it, not by reasoning
> about the Dockerfile. Add scheduled backups (`backup_db()`/`backup_uploads()` every
> 24 hours via APScheduler, pruning anything older than a configurable `keep_days`,
> default 7) and a manual admin-triggered backup, both emitting structured
> `*_backup_created`/`*_backup_failed` events. Build `run_startup_steps()` as one
> deterministic, ordered sequence — DB connect and migrate, Telegram webhook sync,
> conditionally start the scheduler and run the auto-backup check based on
> environment, each failure appending a named reason code to a `degraded_reasons`
> list — ending in one structured `startup_summary` log line with an overall
> `ready`/`degraded` status. Catch specific exception types at each step
> (`sqlite3.Error`, `OSError`, `ValueError`), never a bare `except Exception`."

## Generalized learnings, for projects that aren't this one

The 14 layers above are deliberately literal to ManaVote — real tables, real
thresholds, real tool names — because a prompt sequence that only works in the
abstract doesn't actually get followed. But the findings behind them generalize past
Flask, SQLite, and this domain. Stripped of ManaVote specifics, here's what this
project's history actually argues for anywhere:

1. **Decide your durability model before the first thing that needs it.** Any state
   representing "an operation isn't finished yet" — a pending confirmation, a queued
   job, an idempotency key — belongs in durable storage with an expiry from its first
   line of code, even in a single-process prototype. The question "what happens to
   this if the process restarts right now" is cheap to ask at design time and
   expensive to answer honestly after the fact. *(Generalizes finding 2.)*
2. **Decide your surface model before the second feature.** If anything other than
   the primary client (a bot, a public API, a second frontend) is even plausible,
   put a thin service layer between entry points and business logic now — logic
   that takes its dependencies as explicit parameters, not globals — so the second
   surface calls the same function instead of re-deriving it. *(Generalizes findings
   5, 6.)*
3. **Security and infrastructure hygiene is a zero-feature-value, high-leverage first
   commit, not a per-feature concern.** Request-forgery protection, a vetted
   credential-hashing library, secure-by-default transport with an explicit
   local-development escape hatch, non-debug-by-default, and input validation cost a
   few lines before the first user-facing route and a dedicated audit pass after
   dozens of them exist. *(Generalizes finding 3.)*
4. **Specify every formula in one sentence with one worked example before it's code**
   — anything involving money, a percentage, a threshold, or a ranked/scored value —
   and write the test that checks that example before the formula appears anywhere
   else (a UI, a report, a second code path). A number's meaning that only exists as
   the code that computes it has no independent way to be checked. *(Generalizes
   findings 11, 19.)*
5. **A convention isn't a convention until something other than memory checks it.**
   State it in a style guide, then give it a lint rule, a snapshot test, or at
   minimum an explicit instruction for what a reviewer (human or agent) checks a diff
   against — a rule that only exists as prose gets violated by the first person (or
   agent) who hasn't memorized it. *(Generalizes findings 7, 21.)*
6. **Every "second" thing is where an unwritten assumption gets found.** A second
   auth method, a second surface, a second contributor, a second commit touching the
   same feature, a second container recreation — each one tests every assumption the
   first version made without saying so. Before adding any of these, list what the
   existing implementation assumes that isn't written down, and check the new thing
   against each assumption explicitly — especially anything touching identity,
   money, or a destructive action. *(Generalizes findings 13, 16, 17, 20.)*
7. **Ship vertical slices, not layers, and prove the happy path before merging.**
   Acceptance criteria (with edge cases) before code; tests against those criteria
   before or alongside the implementation; one real end-to-end pass of the actual new
   page/endpoint's happy path before calling it done — a passing unit-test suite is
   not the same claim as "a user can actually do this." *(Generalizes finding 12.)*
8. **A protocol-compliance surface needs a real external client before "done."**
   Implementing to a written spec (an API contract, a bot platform's rules, a plugin
   interface) is necessary but not sufficient — test against one real reference
   client or consumer before calling the surface finished, because request-shape and
   naming mismatches only show up against real traffic. *(Generalizes finding 14.)*
9. **Scope any migration to the smallest unit that proves the pattern, and prove the
   build story for that unit before widening.** One component, one table, one
   endpoint — with its contract written down as a tested invariant, not a comment —
   beats a big-bang rewrite that needs an immediate follow-up fix. *(Generalizes
   finding 8.)*
10. **Verify infrastructure claims against the real mechanism, not code review.**
    If something must survive a restart, a redeploy, or a rebuild, prove it by
    actually doing that once, rather than reasoning about whether the configuration
    should work. *(Generalizes finding 16.)*
11. **When a decision is ambiguous, hard to reverse, or touches security, money, or
    identity, the right move is to stop and ask — not to silently pick a reasonable
    default.** Nearly every finding in this document is a decision that seemed
    reasonable when made and only became a problem once something else depended on
    it without knowing it was ever a choice. An agent (human or AI) that surfaces
    those moments instead of resolving them silently is the actual fix, upstream of
    every layer- and finding-specific lesson in this document.
12. **Keep every commit to one concern.** It costs nothing in the moment and it's the
    difference between a retrospective like this one being possible at all and a
    project whose own history can't answer "when did this start, and why."
    *(Generalizes finding 10.)*

### The one prompt to give at the start of any project

This is the prompt version of the list above — generic on purpose, meant to be pasted
once at the start of a new project (with a coding agent or without one) and revisited
explicitly whenever a new external integration, auth method, or client is added, not
just used once and forgotten.

> **Prompt:** "Before writing any feature code for this project:
>
> 1. Start a living spec file naming every core entity and the exact identifier each
>    of its states will use in code, not a display label to be chosen later. If a
>    user-facing label will ever differ from that identifier, write both down
>    together now.
> 2. For every calculation involving money, a percentage, a threshold, or a
>    ranked/scored value that the system will ever compute: write its definition as
>    one sentence with one worked numeric example, and plan a test that checks that
>    example before the formula is implemented anywhere else.
> 3. Tell me explicitly: will this run as more than one process (multiple workers, a
>    restart, a redeploy)? Will anything besides the primary client ever need to do
>    what this does (a bot, an API, another frontend)? If either is plausible: put a
>    thin service layer between entry points and business logic now (dependencies
>    passed explicitly, not read from globals), and store anything representing 'this
>    isn't finished yet' (a pending action, a job, an idempotency key) in durable
>    storage with an expiry, not in memory, even though we only run one process today.
> 4. As one dedicated commit before any user-facing feature: add request-forgery
>    protection, a vetted credential-hashing library, secure-by-default
>    transport/cookies with an explicit escape hatch for local development,
>    non-debug-by-default, and input/upload validation. Treat this as infrastructure,
>    not a feature — don't revisit it per-feature later.
> 5. Start a conventions doc. For every convention in it (a shared UI/component
>    system, a commit-message rule, a testing expectation), also state how it's
>    checked — a lint rule, a snapshot test, or at minimum an instruction for what a
>    reviewer checks a diff against. A convention that only exists as a sentence
>    isn't enforceable.
> 6. Build every feature as one vertical slice: acceptance criteria including edge
>    cases, then tests against those criteria, then implementation using
>    already-established shared components, then one real end-to-end pass of the
>    actual new page/endpoint's happy path before calling it done. Keep every commit
>    to one concern — if what I ask for bundles more than one, say so and propose
>    splitting it rather than doing both silently.
> 7. Before adding a second surface, provider, or consumer of any existing logic (a
>    second API shape, a second auth method, a second client): extract the shared
>    logic into one function/service both will call, with a test asserting they
>    agree; and list every assumption the existing implementation makes that isn't
>    written down, checking the new one against each explicitly — especially
>    anything touching identity, money, or a destructive action.
> 8. Test any protocol-compliance surface (an API contract, a bot integration, a
>    plugin interface) against one real external client or reference implementation
>    before calling it done — not just against your own reading of its spec.
> 9. Scope any framework, infrastructure, or schema migration to the smallest unit
>    that proves the pattern. Write its contract down as a tested invariant, and
>    verify the build/deploy story for that one unit before proposing to widen it.
> 10. If something needs to survive a restart, a redeploy, or a rebuild, prove it by
>     actually doing that once before calling it shipped — not by reasoning about
>     whether the configuration should work.
> 11. When a decision is ambiguous, hard to reverse, or touches security, money, or
>     identity: stop and ask me to make and document the decision explicitly, rather
>     than picking a reasonable-looking default silently.
>
> Revisit this list explicitly before starting any new external integration, auth
> method, or client — not just once at project start."

## How to use this file

This is a retrospective, not a backlog — none of the findings above are Sprint
candidates by themselves (most of what they describe has since been fixed; see
`SPRINTS.md`/`IDEAS.md` for the current, forward-looking backlog). Their job is
narrower: the next time this project (or its next major surface) is tempted to skip one
of these for speed, this is the receipt for what skipping it cost last time. The layer
sequence above is the same evidence turned forward instead of backward, made literal:
it's not a generic template but this specific app's actual entities, thresholds, tables,
and tool names, ordered so each layer depends only on layers already built. If the
app were deleted today, following the fourteen layers in order — adapting only what a
real rebuild would legitimately change — is a defensible way to reconstruct its current
behavior without reproducing the roughly 48 commits of rework this document tallies.
