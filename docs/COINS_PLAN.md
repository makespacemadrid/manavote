# Coins — Product and Implementation Plan

## 1. Goal

Add a signed-in member page named **Coins**, immediately before **Group purchases** in
the primary navigation. Members use it to record stock leaving the space when they
consume an item and stock entering the space when they replenish one. The same events
debit or credit each member's ManaVote coin ledger, so members can see and balance what
they owe the space.

The initial catalogue is:

1. Coke
2. Coke Zero
3. Other Can

For the MVP, one consumed can debits one coin and one replenished can credits one coin.
Coins represent units contributed versus consumed, not euros or a cash payment method.

## 2. Product decisions for the MVP

- **Every movement is attributable.** Web and Telegram actions use the authenticated,
  linked member. No anonymous stock changes are accepted.
- **Consumption defaults to one.** The common action is one tap; a member may instead
  choose a positive integer quantity.
- **Replenishment requires a quantity.** The UI suggests common quantities but never
  assumes a crate size.
- **The starting cans use a 12-pack shortcut.** Coke, Coke Zero, and Other Can each show
  an **I bought 12** button that records a replenishment of 12 and credits 12 coins.
- **A member balance is explicit.** Consumption reduces it and replenishment increases
  it. A negative balance is a debt in coins; a positive balance is a contribution.
- **History is append-only.** Corrections are compensating entries rather than edits or
  deletes, preserving an audit trail.
- **Stock may go below zero.** A negative stock count is a useful discrepancy signal and
  must be visible, not silently rejected. Admins can reconcile it with an adjustment;
  this is distinct from a member's coin balance.
- **All three channels share one service.** Web forms, QR landing flows, and MCP call
  the same validation and transaction boundary.
- **The catalogue is seeded, not hard-coded into transactions.** The three starting
  items are database rows so more items can be added later without redesigning the log.
- **Admins can extend the catalogue.** Each new item has a unique name and configurable
  purchase pack size, which drives its quick action (for example, **Icecream Minis mix**
  with an **I bought 8** button).

## 3. Member experience

### Coins page (`GET /coins`)

Display three item cards in the seeded order. Each card includes:

- item name and current quantity;
- the signed-in member's coin balance, with debt and credit explained in plain language;
- a prominent **Consume 1** action;
- a **Replenish** action with quantity input;
- a prominent **I bought 12** action for each of the three initial items;
- a compact quantity selector for consuming more than one; and
- links/buttons to the item's consume and replenish QR codes.

Below the cards, show the signed-in member's latest movements with item, action, quantity,
source, and timestamp. Named global history is admin-only. The member view should not
expose transport secrets or raw QR tokens.
Use Post/Redirect/Get so refreshing the success page cannot repeat a movement.

Accessibility requirements: real form labels, keyboard-operable actions, status text in
addition to colour, focus returned to the affected card, and a live success message such
as “Consumed 1 Coke — 11 remaining; your balance is -2 coins.” Replenishment should say
both how many units were added and how many coins were credited. Add all copy to both
existing language catalogues (English and Spanish).

The page must explain the ledger before the first action: consuming one item deducts one
ManaVote coin; replenishing one item adds one coin. The **I bought 12** shortcut is a real
replenishment entry, not a debt-forgiveness control: it adds 12 cans to stock and credits
the member 12 coins in the same transaction.

### QR flow

Provide **two QR codes per item**, one for consume and one for replenish. A QR encodes a
stable application URL, not an MCP API key and not a direct mutation:

```text
/coins/scan/<opaque-random-token>
```

After scanning:

1. An unauthenticated visitor is sent through login and returned to the scan URL.
2. The landing page identifies the item and action.
3. Consume presents a one-tap confirmation defaulting to 1; replenish asks for quantity
   and offers **I bought 12** for the three seeded items.
4. A CSRF-protected `POST` records the movement and shows the new balance.

Tokens map server-side to `{item_id, action, active}` and can be rotated or disabled.
They are locators, not bearer authorization: a valid login and explicit POST remain
required. Add an idempotency nonce to the confirmation form and enforce it uniquely in
the database to prevent double taps, retries, and browser resubmission.

### Printable QR labels in Admin

Add a **Coins QR labels** section to Admin. It shows print-ready labels for every active
item/action pair and a **Print labels** control. Each label must contain:

- the item name in large, high-contrast type (the dominant text on the label);
- an unambiguous **Consume** or **Replenish** heading;
- the QR code and a short fallback URL/code;
- a plain-language explanation of the ledger effect; for example, **“Taking one Coke
  debits 1 ManaVote coin from your ledger”** or **“Adding Coke credits 1 ManaVote coin
  per can”**; and
- a reminder that the member will sign in and confirm before anything is recorded.

Use a dedicated printable route (`GET /admin/coins/qr-labels`) and print stylesheet that
hides navigation/actions, preserves QR contrast and quiet zones, avoids splitting a
label across pages, and supports common A4 label/card layouts. The printable view must
render server-side and remain usable without JavaScript. Admins can preview, print,
disable and rotate tokens. The opaque token is persisted because printable labels must
be reproducible; it is a locator and never authorizes a mutation by itself. Add an
automated rendering test and manually scan a printed consume and replenish label before
release.

### Telegram bot through MCP

Expose these tools to linked members under the existing `MEMBER_WRITE` policy:

- `consume_coin_item(item, quantity=1, idempotency_key?)`
- `replenish_coin_item(item, quantity, idempotency_key?)`
- `list_coin_items()` for discovery and current stock
- `list_coin_movements(item?, member_id?, limit=20, offset=0)` for history

The Telegram adapter must remove `member_id` from the model-visible schema and bind the
actor to the linked Telegram account, as it already does for member feedback. These
ordinary member writes do not require the admin `/confirm` flow. Tool results should
contain the item, inventory delta, coin delta, resulting stock, resulting member coin
balance, movement ID, actor, and timestamp so the bot can give a deterministic
acknowledgement.

Accept names case-insensitively and return a disambiguation/validation error rather than
guessing unknown items. Example phrases to cover in tests include “I took a Coke Zero”,
“I added 24 Coke”, and “what cans are left?”.

## 4. Data model

Use an immutable movement ledger. Derive stock with `SUM(inventory_delta)` and each
member's coin balance with `SUM(coin_delta)`:

```sql
CREATE TABLE coin_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    position INTEGER NOT NULL DEFAULT 0,
    pack_size INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE coin_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    inventory_delta INTEGER NOT NULL,
    coin_delta INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('consume', 'replenish', 'adjustment')),
    source TEXT NOT NULL CHECK (source IN ('web', 'qr', 'mcp', 'admin')),
    idempotency_key TEXT NOT NULL UNIQUE,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES coin_items(id),
    FOREIGN KEY (member_id) REFERENCES members(id),
    CHECK (inventory_delta <> 0 OR coin_delta <> 0),
    CHECK (kind = 'adjustment' OR inventory_delta = coin_delta)
);

CREATE TABLE coin_qr_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE,
    item_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('consume', 'replenish')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES coin_items(id)
);
```

Add indexes on `(item_id, created_at DESC)` and `(member_id, created_at DESC)`. QR tokens
are opaque random locators, not credentials; login, CSRF, and confirmation still protect
every mutation. Seed catalogue rows with `INSERT OR IGNORE` in the idempotent migration
path and mirror the tables in `schema.sql` for fresh installs.

For member actions, `inventory_delta` and `coin_delta` are both negative for consumption
and both positive for replenishment. Admin stock reconciliation may use a zero
`coin_delta`, so correcting a physical count never changes a member's debt. Only the
service may translate a public action and positive quantity into signed values; clients
must not submit arbitrary deltas. Put a conservative configurable upper bound (proposed
MVP default: 1,000 units per action) in service validation. Seed the three initial items
with `pack_size = 12`; future items may leave it null or choose another shortcut.

## 5. Code shape

Follow the repository's thin-route and shared-business-rule conventions:

- `app/repositories/coin_repo.py`: item lookup, atomic movement insert, inventory and
  per-member coin balance/history queries, token lookup, and catalogue reads.
- `app/services/coin_service.py`: normalize item names, validate action/quantity,
  generate idempotency keys, bind actors, record structured outcomes, and translate
  duplicate keys into a stable replay response.
- `app/web/routes/coin_routes.py`: authenticated page, normal form POST, scan landing,
  scan POST, printable labels, and admin-only token rotation/adjustment endpoints.
- `templates/coins.html` and `templates/coin_scan.html`: progressively enhanced server
  forms; JavaScript must not be necessary to record a movement.
- `app/mcp_server.py`: definitions and dispatch for the four tools, delegating writes to
  the same service.
- `app/services/mcp_tool_registry.py`: explicit Telegram policies; deny-by-default
  behavior remains intact.
- `app/db/schema.sql` and `app/db/migrations.py`: fresh and existing database paths.
- `translations.py`: English and Spanish UI/result/error strings.

Register the Coins blueprint and insert its navigation entry immediately before Group
purchases. Preserve the server-rendered/React hydration contract by changing navigation
props, fallback markup expectations, and tests together.

## 6. Security, integrity, and observability

- Require login for all member pages and mutations; require admin for adjustments,
  catalogue management, and QR rotation.
- Keep CSRF enabled on web/QR POSTs. MCP continues to use its transport authentication
  plus application-layer actor policy.
- Never put an MCP key, member identity, quantity, or mutation instruction in a QR code.
- Insert a movement and calculate its resulting stock and member coin balance in one
  database transaction.
- Treat a repeated idempotency key as the original success, not as a second movement.
- Rate-limit scan submissions and MCP writes without making normal multi-can entry
  painful.
- Emit structured events with `event=coin_movement_recorded`, `movement_id`, `item_id`,
  `member_id`, `kind`, `inventory_delta`, `coin_delta`, `source`, `resulting_stock`, and
  `resulting_coin_balance`; never log QR tokens.
- Admin views should highlight negative balances and allow export/reconciliation later,
  but those are not required to launch the member workflow.

## 7. Delivery slices

### Slice 1 — Ledger and service

1. Add idempotent schema/migration and seed the three items.
2. Implement repository and service with consume, replenish, stock, per-member coin
   balance, and history.
3. Add unit tests for validation, signed deltas, negative stock, concurrency transaction
   behavior, idempotent replay, item matching, and missing/inactive items.

### Slice 2 — Coins page

1. Add blueprint registration and `GET /coins` plus CSRF-protected mutation POST.
2. Add translated templates, the seeded **I bought 12** shortcuts, and place Coins before
   Group purchases in navigation.
3. Add route, template, translation-coverage, hydration, and authorization tests.

### Slice 3 — QR workflows

1. Generate opaque consume/replenish token mappings and render downloadable QR images.
2. Add authenticated landing and confirmation flows with return-after-login behavior.
3. Add the Admin preview/print route with large item names, ledger explanations, fallback
   text, and print CSS.
4. Test invalid/disabled tokens, CSRF, double submission, authorization, label rendering,
   and token rotation. Manually verify both codes from paper with a physical phone before
   release.

### Slice 4 — MCP and Telegram

1. Add list/history and consume/replenish tool schemas and dispatch.
2. Classify tools explicitly; bind Telegram writes to the linked member.
3. Test raw MCP authentication/validation, Telegram policy filtering, actor spoofing,
   duplicate delivery/idempotency, natural-language examples, and response formatting.
4. Document the tools and operational logs in `APIDOC.md` and `OPERATIONS.md`.

## 8. Acceptance criteria

- Coins appears directly before Group purchases for signed-in members.
- Coke, Coke Zero, and Other Can exist exactly once after both fresh initialization and
  repeated migrations.
- A member can consume or replenish from the page, from each action-specific QR flow,
  and through the linked Telegram bot/MCP path.
- Each initial item has an **I bought 12** action that atomically adds 12 units and credits
  the acting member 12 coins.
- Every successful action creates exactly one attributable immutable movement and all
  channels report the same resulting stock and member coin balance.
- Admin can print action-specific QR labels whose largest text is the item name and whose
  copy clearly states whether scanning ultimately debits or credits the ManaVote ledger.
- Admin can create a new item category with a pack size; it appears on the member page
  and receives consume/replenish QR labels without a deployment or schema change.
- Refreshes, duplicate Telegram updates, and retrying an idempotency key do not change
  stock twice.
- Unauthenticated QR visitors must log in; unlinked Telegram users cannot write; one
  member cannot select another member as actor.
- Invalid quantities, inactive/unknown items, disabled tokens, missing CSRF, and missing
  MCP authentication fail without a movement.
- Negative stock is displayed clearly and logged, not rejected or hidden.
- English and Spanish copy, relevant API/MCP docs, migrations, structured logs, and the
  full regression suite are complete.

## 9. Decisions to confirm before implementation

The MVP uses a global balance across item types: replenishing any item can offset a debt
from another item. The remaining decisions do not block the ledger-first architecture,
but should be settled before UI polish:

1. Who may replenish: every linked member, or admins/stewards only?
2. Should `Other Can` remain one pooled item, or should the replenishment flow capture an
   optional can description?
3. Where will QR labels be mounted, and should one label contain two codes or should each
   action have its own label?
