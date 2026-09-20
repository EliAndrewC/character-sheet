# Audit: front-end-only rules, and concurrent writers

**Written** 2026-09-20 by this repository's Claude Code session, against the tree that implements
`discord-design/requirements.md` (Part 4 of that file asks for this). Line numbers are as of that
commit and will drift; function names are the durable handle.

**How to read a finding.** Each says what it is, where it lives, and what was decided. A decision
to leave something alone is recorded WITH the alternative that was declined, so a later session can
tell a deliberate limitation from a bug. Findings marked **[verified]** were read in the code by the
session that wrote this; findings marked **[reported]** came from a sweep and were not individually
re-read - treat the line numbers as leads, not facts. One sweep claim was checked and found FALSE
and is listed at the end so nobody re-discovers it.

The topology that bounds everything in Part B: **one uvicorn worker, on one Fly machine, holding the
SQLite file on a volume** (`Dockerfile` has no `--workers`; `fly.toml` has one `[[vm]]` and a
`[mounts]` block). Every race here is between requests inside one process. If anyone ever adds a
second worker or a second machine, the in-process guarantees in B0 stop holding and B1-B9 all need
re-reading. SQLite-on-a-volume is what is holding that line.

---

# Part A - rules and state transitions that exist only in the browser

The server's rule engines are `services/dice.py` (formula construction), `services/roll_engine.py`
(rolling a formula), `services/void_spend.py`, `services/tracking.py`, `services/nights_rest.py`,
`services/xp.py` and `services/status.py` (money). `POST /characters/{id}/track` is a setter: it
clamps the wound and void integers, sanitizes `action_dice` / `precepts_pool`, and stores
`adventure_state` **verbatim, with no schema**. So every rule about WHAT goes into
`adventure_state` is a browser rule. That is the root of most of this list.

`roll_math.js` exports about 45 functions. The ones with a Python twin, and what pins them:

| JS | Python | pinned by |
|---|---|---|
| `allocateVoidSpend`, `applyDiceCap` | `void_spend.allocate_void_spend`, `roll_engine.apply_dice_cap` | `tests/shared/void_spend_cases.json` (one table, both suites) |
| `initiativeSortValue`, `initiativeActionValues` | `roll_engine.initiative_sort_value`, `initiative_action_values` | `tests/shared/initiative_cases.json` (one table, both suites) |
| `applyTotalCap`, `altCap`, `altTotal`, `visibleAlternatives` | same names in `roll_engine.py` | parallel cases in `tests/test_roll_engine.py` and `tests/js/roll_math.test.js` |
| `isImpaired` | `dice.is_impaired` | separate tests |
| `pcp*` | `xp.pcp_total_cost` etc. | separate tests |

Everything else in `roll_math.js` is browser-only combat arithmetic.

## A0. Moved to the server by this work

| rule | now lives in | browser |
|---|---|---|
| per-roll void cap, `worldliness_max`, void max | `void_spend.void_limits` | `pages.py` renders from the same call |
| what a school does on a void spend (Ide 5th, Yogo Warden 3rd, Matsu 3rd) | `void_spend.spend_consequences` + `apply_void_spend` | `deductVoidPoints` reads the same flags via `school_abilities` |
| void draw order | `void_spend.allocate_void_spend` | JS copy kept (the spend menu is built with no round trip); shared case table |
| Commune's activation point | `void_spend.plan_void_spend(activation_cost=...)`, charged by the command layer | unchanged |
| initiative: keep-lowest, Kakita sort, Hiruma / Shinjo / Kakita transforms, Togashi extra die, Mantis 4th Dan die | `roll_engine.execute_initiative` | arithmetic moved from `_dice_js.html` into `roll_math.js`; shared case table |
| starting a combat round | `tracking.start_combat_round`, `PER_ROUND_STATE_KEYS` | `setActionDice` unchanged; Night's Rest now reuses the same key tuple |
| Priest 5th Dan conviction refresh at round start | `tracking.conviction_refreshes_each_round` | **the requirements missed this one** - it was in `_resetPerRoundAbilities`, not `setActionDice` |
| Shosuro 5th Dan "lowest 3 dice added" | `roll_engine.execute_roll` | **[verified]** the server's roller did not apply it at all, so `/etiquette` for a 5th Dan Shosuro came out lower than the sheet. Fixed. |
| "Capped at N by Withdrawn" card bullet | `roll_engine.execute_roll` | the server's card omitted it. Fixed. |

Still two copies on purpose: the browser ROLLS its own dice (animation, and Read-only Roll Mode,
where a non-editor's roll must never reach the server). Declined alternative: have the browser ask
the server to roll. It would remove the duplicate, but it would put a round trip inside every roll
animation and would need a no-persist mode for non-editors. The shared case tables are the cheaper
way to keep two copies honest.

## A1. Known discrepancy left for the GM **[verified]**

**Mirumoto 5th Dan "+10 per void point on combat rolls"** is applied by the sheet's `executeRoll`
(`_dice_js.html`, the `combat_vp_flat_bonus` block) to **every** roll that goes through it - a
Sincerity roll included. `school-features/MirumotoBushi.md` quotes the rule as "on combat rolls".
The server-side roller does NOT add it, because every roll a slash command can make is non-combat.
So for a Mirumoto at 5th Dan, `/sincerity void:1` and the same roll on the sheet differ by 10, and
the sheet is the one that looks wrong. Not changed here: it is a rules call on a school nobody asked
about, and "fix" means deciding which roll keys count as combat. Flagged rather than guessed.

## A2. Bugs found while looking, and fixed

- **Bayushi 4th Dan banked a free raise after every roll [verified, fixed].** The grant in
  `runRoll`'s post-roll hooks had no `key === 'knack:feint'` guard, unlike the feint temp-VP grant
  directly above it. The rule is "after a successful or unsuccessful feint". One-token fix.
- **`save()` dropped saves [verified, fixed]** - see B1.

## A3. Bugs found and NOT fixed

- **Mirumoto 3rd Dan round points are never persisted [verified].** `mirumotoRoundPoints` is
  initialized to a literal `0` in `trackingData()` and only refilled by an initiative roll, so a
  page reload mid-round zeroes the pool. Fix: an `adventure_state` key plus an entry in
  `PER_ROUND_STATE_KEYS`. Small. Left because it changes what a reload does mid-combat and deserves
  its own clicktest rather than riding along here.
- **Shinjo 3rd Dan parry decrement can go negative in the tab and is clamped on save [verified].**
  The post-parry loop does `d.value -= X` with no floor; `_sanitize_action_dice` clamps to 0..10, so
  the value differs before and after a reload, and the phases-held bonus with it. Needs a rules
  answer (can an action die go below 0?) before a code answer.
- **Priest 5th Dan ally conviction: the per-roll cap is client-only [reported].** `/ally-conviction`
  clamps to the POOL (`2 x rank`) but not to `rank` per roll. Enforcing it needs a roll identifier in
  the request.
- **`/precepts-pool` accepts any pool from an ally [reported].** Whole-list replace with no check
  that the posted pool is a legal successor of the stored one. See B4.

## A4. Browser-only, would be needed by a non-browser caller, not moved

Ordered by how soon a slash command would hit them. Costs are for moving the RULE, assuming A5's
prerequisite where noted.

| rule | where | cost | note |
|---|---|---|---|
| wound-check result: pass/fail, serious wounds per 10 failed, Bayushi 5th halving | `roll_math.js` `woundCheckResult` & friends | small | pure integers. First thing `/woundcheck` needs. |
| taking serious wounds / LW reset; Yogo temp VP per SW | `applyWoundCheckFailure`, `wcTakeSeriousAndReset`, `lwTakeSeriousAndReset` | small-medium | the passed-check branch is a player CHOICE, so the endpoint takes a `choice` |
| banks granted at a wound check (Isawa Duelist 5th, Akodo 3rd) | `wcKeepLightWounds` | small | |
| per-adventure reset | `resetAdventure` in `_tracking_js.html` | small | `nights_rest.py` already has most of the key list; a GM "reset the party" command is impossible without it |
| per-day pool reset | `resetAbility` | small | `_per_day_pool_ids` already enumerates them |
| action-die selection (lowest unspent; athletics-only skip; Mantis 3rd picks highest; Kakita interrupt spends two highest) | `_tracking_js.html` | small | any combat command must consume a die |
| eight banked-bonus stores (Akodo, Matsu, Hiruma, Bayushi, Hida, Shinjo, Isawa Duelist, Ide) | grant and spend scattered over four roll flows; one funnel, `saveBankedBonuses` | medium | shapes are inconsistent (int / list / list of `{amount, spent}`), and a legacy-format migration exists only in JS. Only Matsu's GRANT is server-side (it rides the void spend). Auto-consumed ones (Hiruma, Hida, Ide) would make a server-side attack total WRONG, not merely less convenient |
| Mantis posture tracker and its flat bonuses | `_tracking_js.html` + five reads of `currentPosture()` in the roll flows | medium | the formula layer has no notion of live combat state |
| Togashi 5th Dan heal, Hida 4th Dan trade, Akodo 5th reflect, Akodo/Courtier temp-VP grants | **inline `@click` strings** in `tracking.html`, `modal_result.html`, `modal_wound_check.html`, `modal_attack.html` | small each | not unit-testable where they are; extracting them into named functions is the prerequisite for anything else. The Togashi heal hand-rolls the void draw order that `allocate_void_spend` already implements |
| pools: Conviction, Otherworldliness, Worldliness, Lucky, 3rd Dan free raises, Togashi daily raises | availability / cap / spend / undo all in `_dice_js.html` | small-medium | server knows only the maxima; `/track` accepts any integer for any `_used` key |
| Lucky / PCP / Merchant rerolls; Merchant 5th Dan selective reroll; Merchant post-roll void; Priest impaired-10s ritual | `_dice_js.html` | **large** | a reroll is a second interaction on a roll the server has already resolved; needs a stateful roll or a `PATCH .../reroll`. Six per-flow reroll cores would have to converge first |
| attack resolution | `rollAttack` | **large** | about a dozen terms need OPPONENT input (TN, defender phase, was-I-attacked-this-round) that has no representation in the data model. The rule count is not the obstacle; the missing request schema for "the situation" is |
| damage assembly - FOUR separate implementations (`atkComputeDamage`, `duelComputeDamage`, `rollKakita5thDanDamage` with the 10k10 cap hand-inlined, `rollSubDamage` with its dice computed inside `@click` strings) | `_dice_js.html`, `modal_result.html` | **large**; consolidating first is medium | porting four divergent assemblers means porting four sets of bugs |
| parry resolution + post-roll hooks (Mirumoto temp VP, Shinjo decrement, Hiruma bank) | `_dice_js.html` | medium | |
| iaijutsu duel state machine | `_dice_js.html`, `modal_duel.html` | **large** | genuinely multi-round and interactive. `duelTn` (XP / 10) alone is a one-liner worth extracting |
| Kakita 5th Dan once-per-round latch | `adventure_state.kakita_5th_dan_used` | medium | the server CLEARS it (round start, Night's Rest) but does not enforce it |

Already server-side and confirmed so: **Night's Rest** (`services/nights_rest.py`; the client only
renders the plan and reloads), the **money ledger** (item-level routes keyed by entry id; the client
holds no balance), and the **PCP ledger** (`/spend-pcp` owns the count and the version). The ledger
is the model the rest should follow.

## A5. The structural point

Most of A4 is "small" individually and blocked collectively by the same thing: **`adventure_state`
has no server-side schema and `/track` will store anything.** Giving it one - a set of validated
operations (spend from pool P, bank bonus B, start round, reset adventure) instead of one blob
setter - is the change that turns `/track` from a setter into a rule boundary. That is a real
architectural change, measured: `save()` is called from 45 sites across six templates, and the
`setCount` / `setToggle` helpers fan out further. It was deliberately NOT attempted here. What was
done instead is B1: the blob setter is now safe against concurrent writers, which is what the slash
commands needed, and each operation above remains free to move server-side one at a time, the way
void spends and initiative just did.

Suggested order when someone does want it: (1) extract the inline `@click` rules into named JS
functions; (2) port the pure wound-check math, which unblocks `/woundcheck`; (3) the three resets;
(4) the pools; (5) the banks. Attack, damage, parry and the duel wait for a data model of the
opposing side.

---

# Part B - concurrent writers

## B0. The class fix, part one: a handler's read-modify-write is now atomic **[fixed]**

Nearly every write route is an `async def` that loads a row, THEN does `await request.json()`, then
mutates and commits. That `await` is a real suspension point in the middle of a read-modify-write:
a second request could load, change and commit the same row inside the gap. It is what made even
the well-designed delta endpoint (`/ally-conviction`, `+1`/`-1` with a server-side clamp) lossy.

`database.prefetch_body` is a router-level dependency on the `characters`, `pages` and `rolls`
routers that reads the body before the handler starts. Starlette caches it, and awaiting a cached
body never yields to the event loop, so everything from a handler's first query to its commit now
runs uninterrupted - which, in the one-worker topology above, makes it atomic. A new route is
covered by being on the router; nobody has to remember anything.

What it does NOT cover, and why that is acceptable today:
- a handler that awaits something else between load and commit. The Google Sheets callback does (a
  multi-second API call), and it writes only its own two columns (B8).
- sync `def` routes, which run on the threadpool. The art routes are the only ones; they write only
  the five art columns.
- a second worker or machine.

Declined alternative: `BEGIN IMMEDIATE` / explicit SQLite transactions around each RMW. More
robust against a future second worker, but it is two dozen call sites and SQLite would still
serialize them. Revisit if the topology ever changes.

## B1. `POST /characters/{id}/track` - whole-state write **[fixed]**

Three ways to lose an update, all **[verified]**:
1. **Two tabs.** Tab A spends a void point; tab B, still holding void = 2, takes wounds and posts
   its whole state; the point is refunded.
2. **A cross-character writer.** An ally spends the priest's conviction (`/ally-conviction`) or swaps
   from his pool (`/precepts-pool`); the priest's own tab then saves its render-time
   `adventure_state` / `precepts_pool` and silently hands it back. Two different people at the same
   table in the same round - the designed use of the feature, not an edge case. This was the worst
   instance in the codebase.
3. **`save()` dropped saves.** `if (this._saving) return;` discarded any save requested while one
   was in flight. Because `save()` sends a whole snapshot, that only mattered when the dropped save
   was the LAST of a burst - three quick clicks on "VP -" against a cold Fly machine left the server
   two behind the screen until some unrelated save happened along, or until a reload "restored" the
   points.

**The fix: `Character.tracking_rev`.** Bumped by an ORM `before_update` listener whenever a column in
`TRACKING_COLUMNS` actually changes - hooked there rather than in each route so that EVERY writer
participates by existing (R4.3 / R4.4): `/track`, Night's Rest, the PCP void refresh, a party
member's conviction spend, the Discord commands, whatever comes next. `/track` requires `rev`; a
mismatch - or no `rev` at all - is `409 {"error": "stale", "tracking": {...}}` and nothing is
written. The tab then `adoptServerState()`s (every counter and every value derived from
`adventure_state`, the dice roller's copies of the banked bonuses included) and shows a notice that
its last change was not applied. No reload. `save()` now queues exactly one follow-up instead of
dropping, and sends `keepalive: true` so a save made just before navigating away still lands.

Decisions worth knowing:
- **A revision counter, not `updated_at` or an ETag.** `updated_at` moves on every editor autosave,
  which would make each open sheet tab stale for changes that cannot conflict with it.
- **Not SQLAlchemy's built-in `version_id_col`**, for the same reason: it versions the whole row.
- **Adopt, do not merge or auto-retry.** After a 409 the tab cannot replay its change: its "change"
  is a whole snapshot, not a delta, and replaying it IS the bug. So the player is told, and makes
  the change again against numbers they can now see. Declined alternative: field-level updates,
  which would let non-conflicting changes compose. That is the better end state and is A5.
- **A missing `rev` is refused.** A tab left open across the deploy will have its saves refused
  until it is reloaded, and that old code does not read the response, so it will not say so. That is
  the safe direction - the alternative is that exactly the tabs most likely to be stale keep
  overwriting - and it lasts only as long as the old tab does.
- **`money_ledger` is NOT under the revision**, although the requirements list it. No tab ever posts
  the ledger whole: its routes add / edit / delete one entry by id, server-side, and with B0 they
  compose. Putting it under the revision would turn every koku entry into a false "changed somewhere
  else" on the player's next wound.
- **The tab that causes a server-side bump adopts the new revision** so it is not refused by its own
  action: `/spend-pcp` returns `tracking_rev`; Night's Rest reloads the page.

## B2. Editor autosave - two editor tabs **[reported; NOT fixed]**

`POST /characters/{id}/autosave` sends effectively the whole build, and every key present is
assigned. Two editor tabs (or a GM and a player who both have edit access): A raises Fire and
autosaves; B, still holding Fire = 2, edits Honor and autosaves the whole build; A's raise is gone.
The client itself is well built - trailing 1500 ms debounce, in-flight coalescing, a dirty flag
re-armed across the fetch, a 30 s retry, a flush before navigate - so there is no same-tab drop
here; `/track` was the outlier.

`tracking_rev` does not cover this (build columns are not tracking columns, on purpose). **The same
mechanism does**: a second counter, `build_rev`, same listener pattern over the build columns, sent
with every autosave, 409 on mismatch. It is not done here because the RECOVERY is a different
problem: a refused editor cannot silently adopt the server's build over text the user is in the
middle of typing, so it needs a "changed elsewhere - reload / keep mine" prompt and a decision about
what "keep mine" means. High severity, medium likelihood; the next thing to do in this area.

One overlap with B1 **[reported]**: autosave writes `current_void_points` (it refills void to the
ring maximum when rings change on an UNPUBLISHED character), so an editor tab and a sheet tab
genuinely contend for that one column during character creation. That write now bumps
`tracking_rev` like any other, so the sheet tab is refused rather than clobbering or being clobbered
silently. The cleaner fix is to move that write out of autosave.

The legacy form endpoint `POST /characters/{id}` accepts a whole build with no check and is posted
to by no template. Whoever adds `build_rev` should cover it or delete it.

## B3. Publish / discard / revert / PCP **[reported; partly fixed]**

- **PCP double-spend: fixed.** `spendPcp()` had no in-flight guard, so a double-click on a slow
  request could buy two (with `void_refresh`, two void points). It has one now, and B0 makes the
  server-side increment atomic.
- **`version_number` is `latest + 1` with no unique constraint.** B0 closes the in-process race. A
  `UniqueConstraint(character_id, version_number)` is the robust fix and was NOT added: creating a
  unique index on the production database fails if duplicates already exist, so it needs a look at
  the live data first.
- **Discard can destroy more than the diff showed.** The confirm modal lists what will be lost; an
  autosave from another editor after that list renders is discarded too, unlisted. Covered by
  `build_rev` (B2): discard / revert / publish would name the revision the diff was computed against.

## B4. `/ally-conviction` and `/precepts-pool` **[partly fixed]**

The direction that mattered - the priest's own tab erasing an ally's write - is B1 case 2, fixed.
`/ally-conviction` is a delta with a server-side clamp and is now atomic (B0), so two allies spending
at once both count. **`/precepts-pool` is still whole-list replace**: two allies swapping different
dice from the same rendered pool, last write wins. Its docstring argues whole-list replace is the
safe choice; for two concurrent allies it is the opposite - a `{die_in, die_out}` operation applied
server-side would let both swaps survive, and would also close A3's trust hole. Left because it is a
redesign of the swap flow, and it needs two allies swapping in the same second.

## B5. Money ledger **[fixed by B0]**

Item-level and keyed by id - the right design. The remaining hazard was read-modify-write across
the `await` (a player adds an expense while the GM's group award appends a reward: one entry never
existed). B0 closes it. A 409 would have been the wrong tool: the correct outcome of two concurrent
appends is that both entries exist, not that one player retypes theirs.

## B6. Night's Rest **[covered]**

Mostly absolute assignment, so it converges; the page reloads after. It bumps `tracking_rev`, so a
second tab's pre-rest snapshot is refused instead of restoring the wounds the rest just healed.
Not done: having `/nights-rest/preview` return the revision it computed against so that confirm can
prove "what you approved is what was applied".

## B7. Roll history **[reported; left alone]**

Per-row, not per-character, so a character revision is the wrong tool. The payload `PATCH` is gated
on `actor_discord_id` (a second person cannot race your row), payloads are cumulative snapshots
rather than deltas, and the client carries a request-id guard, a pending-payload stash, signature
de-duplication and a `keepalive` flush - that code reads like scar tissue and works. Annotations are
last-write-wins between co-editors. Left.

A slash command's roll stays amendable on the sheet through that same `PATCH`, as C8 requires.

## B8. Low severity, left alone **[reported]**

- **Dark secret**: the dangerous direction (an editor who cannot see it blanking it) is already
  defended by `merge_dark_secret`. Its own RMW is atomic under B0. The structural fix is two real
  columns instead of a key inside a shared JSON blob.
- **Google Sheets export**: the "exported state" snapshot is taken before a multi-second API call, so
  an autosave in that window can make the staleness badge read up-to-date when it is not. Re-snapshot
  after the call returns.
- **Art**: a long-lived ORM object across an S3 upload, but it writes only the five art columns, and
  SQLAlchemy only emits dirty attributes. Orphaned uploads are already swept.
- **Import jobs**: insert-only, on their own session. Nothing to lose.
- **Profile**: `granted_account_ids` is rebuilt whole from the form's checkboxes, so two profile tabs
  can silently revoke a grant. One user, two tabs, on a settings page.
- **Group admin**: check-then-insert against a unique name gives a 500 rather than corruption.
  `PRAGMA foreign_keys` is off, so deleting a group maintains referential integrity by hand.
- **`database.py`**: no WAL, no explicit busy timeout, no FK enforcement. None of it bites at one
  worker; all of it is worth doing before there are two.

## B9. Does one mechanism cover the class? (A3 of the requirements)

**No - three, each for a different shape of write, and picking the wrong one is its own bug:**

| shape of write | right tool | where |
|---|---|---|
| a client posts a whole object it holds a copy of | a revision the write must name; refuse and hand back the current state | `/track` (done). Editor autosave, discard / revert / publish want the same with a separate `build_rev` (not done) |
| the server applies an operation (append, remove by id, +1) | make the read-modify-write atomic. NEVER a 409 - both operations should succeed | `prefetch_body` (done): the ledger, `/ally-conviction`, PCP, version numbering |
| per-row records | neither; per-row sequencing if it ever matters | roll history (left) |

---

# Checked and found FALSE

- *"Editing an award's source text is overwritten by the next autosave."* The sweep reasoned that
  the 600 ms source POST and the 1500 ms autosave race over `rank_recognition_awards`.
  `onAwardSourceInput` updates the in-memory award before posting, so the autosave carries the new
  text. **[verified]** Not a bug.
