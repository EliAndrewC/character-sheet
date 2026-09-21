> ## Status: implemented 2026-09-20 by this repository's session
>
> Moved here from the repo root (`discord-slash-commands-requirements.md`) and committed. The text
> below the rule is the request as gm-assistant wrote it, unedited. This block is this app's answer.
>
> **Built**: all of Part 1 (R1-R5), all of Part 2 (C1-C8), Part 3 (R6.1), Part 4 (the audit is
> `discord-design/audit.md`), and the Commune wording fix from Part 7. Production notes are in
> `CLAUDE.md` under "Roll slash commands" and "Key Architectural Decisions".
>
> **Where this app did something other than, or more than, what is written below** - each is
> deliberate:
>
> 1. **F1 missed a per-round rule.** Rolling initiative also refreshes a Priest 5th Dan's conviction
>    pool (it was in `_resetPerRoundAbilities`, not `setActionDice`). `start_combat_round` does it.
>    Mirumoto 3rd Dan's round points also refresh each round but are never persisted, so there is
>    nothing server-side to reset (audit A3).
> 2. **The server's roller was already missing two automatic rules**, independent of void: Shosuro
>    5th Dan's "lowest 3 dice added to the result", and the "Capped at N by Withdrawn" card bullet.
>    Both added, so R1.4's "indistinguishable from the sheet" holds for them too.
> 3. **The sheet had a Mirumoto 5th Dan bug that broke R1.4**: it added +10 per void point to every
>    roll, a Sincerity roll included, where the rule says "combat rolls". The GM confirmed it as a bug
>    and it was fixed on 2026-09-21 (`dice.is_combat_roll`, audit A1), so the sheet and the commands
>    now agree.
> 4. **R4.1 lists the money ledger; it is NOT under the revision.** No tab posts the ledger whole - its
>    routes add / edit / delete one entry by id - so a revision would only produce false "changed
>    somewhere else" notices. Its lost-update hazard was the read-modify-write gap, closed for every
>    route at once by `database.prefetch_body` (audit B0, B5).
> 5. **A `/track` write that names NO revision is refused**, not just one that names a stale one. A
>    sheet tab left open across the deploy is refused until reloaded.
> 6. **Open question 1**: a revision counter, `Character.tracking_rev`, bumped at the ORM layer.
>    `updated_at` and SQLAlchemy's `version_id_col` were declined because both move on editor
>    autosaves, which cannot conflict with a sheet tab. **Open question 2**: on `GET /api/characters`,
>    as a `current` object per character; it also carries `tracking_rev`.
> 7. **C6 formats not in the table**: a knack line is the formula label with no `@rank`
>    (`**Name**: **24** Oppose Social (Air)`); Commune with an optional spend is
>    `(1 void to activate, 2 void)` - one parenthesized span.
> 8. **A Discordant character's `void` is refused** on skills and knacks (the formula's
>    `void_blocked`), ephemerally. Commune's activation point is still charged to them, as on the
>    sheet: it is a cost of making the roll, not a spend on it.
> 9. **`/roll` accepts a typed display name** ("Sincerity", any case) as well as the id.
> 10. **Editor autosave had the same whole-object hazard as `/track`**; fixed on 2026-09-21 with a
>     second revision, `build_rev`, and a "changed somewhere else" prompt in the editor (audit B2).
>     That is the answer to A3's "does one mechanism cover the rest": the same mechanism, a separate
>     counter, and a different recovery.
>
> **Verification notes for Part 6**: item 6's refusal is `409 {"error": "stale", "tracking": {...}}`;
> the on-screen recovery is `[data-testid="tracking-stale-notice"]`.

---

# Requirements: Discord roll slash commands, and the server-side state they need

**Written by**: the gm-assistant Claude Code session, 2026-09-20, against this repository at commit
`6c4dd9c`. It is a request FROM that repository TO this one, not a design imposed on this app - if
something here is wrong about how this codebase works, this app's own session is the authority and
should say so rather than build around it.

**Scope**: Parts 1, 2 and 4 are to be built HERE, by this repository's own session, and Part 3
belongs here too - it is the GM's own instruction, just not something that blocks anything. The GM
decided the ownership on 2026-09-20: the commands live in this repo, so the session that owns this
repo should write them rather than have another session edit this tree. gm-assistant's remaining
share is its own roll-capture side, which needs no work from anyone here - only that the posted
message formats in C6 hold, since it pins them with fixtures.

**Why it exists**: the GM asked for more Discord slash commands - a generic `/roll` with
autocompletion, one command per non-combat skill, three rolled school knacks, `/initiative`, and
void points that really come off the sheet. Planning that (gm-assistant feature 211) turned up two
facts about this app that have to be dealt with first. The GM's instruction was explicit: **no
kludgy workarounds in the bot when the right fix is in this app.**

**The sequence the GM set**: this work is implemented and deployed; then gm-assistant verifies it
by behavior (Part 6) and does its own capture-side work. A blocking requirement that did not land
stops that feature rather than earning a workaround, so if something here is deliberately not
built, saying so in this file is far better than leaving it to be discovered by a wrong answer.

---

## Part 0: the two findings

Both measured here at `6c4dd9c`, not remembered.

### F1. Void spending and initiative are BROWSER code

`app/services/roll_engine.py` can roll dice - that is how `/etiquette` works - but the server has
**never deducted a void point or computed an action die**. Both live in the front end:

| behavior | where it actually is |
|---|---|
| void allocation order (temp -> regular -> worldliness) | `app/static/js/roll_math.js`, `allocateVoidSpend` |
| deducting the points, and the school consequences of spending (Ide 5th Dan temp VP, Yogo Warden 3rd Dan light-wound heal, Matsu 3rd Dan banked wound-check bonuses) | `_dice_js.html`, `deductVoidPoints` |
| the per-roll void cap (lowest ring; lowest ring - 1 for shugenja) and `worldliness_max` | built INLINE inside `app/routes/pages.py` (~l.773) - not callable from anywhere else |
| Commune's 1-point activation cost | `_dice_js.html`, `voidActivationCost` / `computeVoidOptions(reserve)` - the server only sets the `requires_void_point` flag (`dice.py` l.1072) and never enforces it |
| initiative: keep the LOWEST dice, then Hiruma 4th Dan (-2, min 1), Shinjo 4th Dan (highest := 1), Kakita (10 -> phase 0), the Togashi extra athletics die, the Mantis 4th Dan value-1 die | `_dice_js.html` ~l.2759-2818. `build_initiative_formula` returns these as FLAGS for the client to apply |
| starting a combat round (replace action dice, reset Mantis round state, clear `kakita_5th_dan_used`, leave `precepts_pool` alone) | `_tracking_js.html`, `setActionDice` |

A slash command, or any other non-browser caller, therefore has no way to do these things
correctly today.

### F2. An open browser tab silently overwrites state written by anything else

`_tracking_js.html`'s `save()` posts the tab's **entire local tracking state** to
`POST /characters/{id}/track`. There is no version check and no field-level update.

So: a player with their sheet open who spends a void point from Discord, then clicks anything on
the sheet that saves, writes their stale void count back and silently refunds the point. Same for
action dice after `/initiative`.

**This is a bug today, not one the commands introduce** - two browser tabs on one character already
do it to each other, and so does a tab racing the `/discord/interactions` handler. The commands
only make it easy to hit. The GM's instruction is that it be **fixed generally, as a class**, not
patched at the two call sites these commands happen to touch.

---

## Part 1: the server-side foundation (blocking)

### R1. Void spending is a server-side operation

**R1.1** The per-roll void cap and `worldliness_max` are computed by a callable function, not
inline in a page route, and `pages.py` calls that same function. The page and any other caller must
not be able to disagree about a character's cap.

**R1.2** There is a server-side operation that, given a character and a number of void points:
- allocates them in the sheet's own order (temp, then regular, then worldliness),
- refuses if the character does not have that many, or if the number exceeds their per-roll cap,
- deducts them from the persisted character, and
- applies every school consequence the browser applies on a spend (Ide 5th Dan, Yogo Warden 3rd
  Dan, Matsu 3rd Dan - whatever the current set is).

**R1.3** It is **all-or-nothing**: either the roll is made and the points are gone, or nothing
happens at all. A refusal must not roll dice, must not write a `roll_history` row, and must not
partially deduct.

**R1.4** A roll made with a void spend produces a payload and a `roll_history` row
**indistinguishable from the sheet's** for the same spend - same formula, same `void_spent` marker,
same rendering on the dice card and in roll history.

**R1.5** The JavaScript and Python copies of any rule that must exist on both sides are pinned to
**one shared table of test cases**, the way `roll_math.js` and `roll_engine.py` already are for the
total cap. Where a rule can move to the server outright and the browser can read the result, prefer
that to keeping two copies.

### R2. Initiative is a server-side operation

**R2.1** There is a server-side operation that rolls initiative for a character and produces the
final action dice - keep-lowest, plus every school and profession adjustment currently applied in
the browser. The result must equal what the sheet produces for the same character and the same
dice.

**R2.2** There is a server-side "start the combat round" operation with the same semantics as
`setActionDice`: the new dice replace the old, all unspent; per-round state is reset (Mantis round
state, `kakita_5th_dan_used`); state that deliberately survives a round - `precepts_pool` - is left
alone. If that set changes later, the server operation is what defines it.

**R2.3** After it runs, opening the character's sheet shows those action dice and they are
spendable in the normal way. Nothing about them should be recognizable as having come from outside
the browser.

### R3. Knack rolls go through the same path

**R3.1** A knack roll can be made through the same server path as a skill roll, with the same
recording rules and the same payload shape. (`build_knack_formula` already produces the formulas;
what is missing is a caller other than the browser.)

**R3.2** **Commune's activation cost is enforced on the server.** The rules say "Spend a void point
and roll this knack"; today only the browser charges it (`voidActivationCost`). The server must
charge that point as part of making the roll, and must refuse the roll outright when the character
cannot pay it - not roll and then fail to deduct. When an optional spend is requested on top, the
activation point is paid first and the optional spend is checked against what remains, matching
`computeVoidOptions(reserve)`.

### R4. Concurrent writers cannot silently clobber each other

**R4.1** Tracking state (void points, temp void, wounds, action dice, `adventure_state`,
`precepts_pool`, the money ledger - the whole `/track` surface) gains **optimistic concurrency**: a
writer that has not seen the current state is rejected rather than allowed to overwrite it.

**R4.2** A rejected browser save **recovers in the UI**: the tab adopts the server's current values
and tells the player something changed, rather than erroring or silently dropping their edit. The
player should never have to reload to get a correct sheet.

**R4.3** The fix is at the `/track` layer (or whatever replaces it), so that **every** writer is
covered - a second tab, the interactions endpoint, the API, a future integration - not just the two
fields these commands touch.

**R4.4** Server-side writes participate in the same scheme, so a command's write makes an open tab
stale rather than being overwritten by it.

Field-level updates instead of whole-state POSTs would also solve this and are arguably the better
end state; gm-assistant has no stake in which is chosen, only in R4.1-R4.4 holding.

### R5. The read-only API

gm-assistant consumes the existing GM API (`GET /api/rolls`, `GET /api/characters`, bearer
`ROLL_QUERY_TOKEN`) to join Discord messages against recorded rolls.

**R5.1** A roll recorded by a slash command must be reachable through `GET /api/rolls` exactly as a
sheet roll is, including any void spend, so the capture side needs no special case. (This should
already hold - it is listed so it gets verified rather than assumed.)

**R5.2** gm-assistant does **not** need a write API. Every write happens inside this app. Please do
not build one.

---

## Part 2: the slash commands themselves (blocking)

This is the layer gm-assistant originally planned to write and the GM reassigned here on
2026-09-20. It is specified as behavior; how this app structures it is its own call, and
`app/services/discord_commands.py` plus `app/routes/discord.py` already carry most of the shape.

### C1. The command set

| command | rolls | options |
|---|---|---|
| `/roll` | any non-combat skill, chosen by autocompletion | `skill` (required, autocomplete), `void` (optional integer) |
| one per non-combat skill - `/etiquette`, `/precepts`, `/sincerity`, ... | `skill:<id>` | `void` |
| `/oppose-social`, `/oppose-knowledge` | `knack:oppose_social`, `knack:oppose_knowledge` | `void` |
| `/commune` | `knack:commune` | `void`, on top of the activation point |
| `/initiative` | `initiative` | none |

23 commands against Discord's per-application cap of 100.

**C1.1** The per-skill set is DERIVED from `game_data.SKILLS`, never hand-maintained. Measured
2026-09-20: `SKILLS` holds exactly the 18 non-combat skills, combat lives in a separate
`COMBAT_SKILLS`, and iaijutsu is a knack - so deriving from that table excludes combat by
construction rather than by a filter somebody has to remember.

**C1.2** The knack set is an explicit allow-list of exactly those three ids. The GM held every
other school knack and school ability back by name for a later feature, so a fourth must not appear
by being rollable.

**C1.3** A guard test asserts both: the registered names equal `SKILLS` plus the three knacks plus
`{roll, initiative}`, and no id from `COMBAT_SKILLS` is reachable through any command. A future
move of attack into `SKILLS`, or a knack added casually, should turn the gate red rather than
quietly register a command.

**C1.4** Discord requires lowercase names with no spaces, so the knack commands are hyphenated
while their roll keys are underscored: `oppose-social` -> `knack:oppose_social`.

### C2. `/roll` autocompletion

**C2.1** `/roll`'s `skill` option autocompletes (Discord interaction type 4, answered with type 8).
Autocomplete cannot be deferred and must answer inside 3 seconds; a dict filter over 18 skills
meets that comfortably.

**C2.2** Matching is case-insensitive, prefix first then substring, over skill names. The choice
value is the skill id; the label is the skill's name. Up to 25 choices, which the full skill list
fits under with nothing typed.

**C2.3** `/roll` completes **skills only**, not knacks. The three knacks have their own commands
and the rest are deferred, so listing any knack would advertise a category this work does not
cover.

**C2.4** An autocomplete request never errors to the user; on any internal failure it returns the
plain list.

**C2.5** The submitted value is re-validated when the command is actually run, since a player can
ignore the completions and type free text. An unknown skill gets an ephemeral error and no roll.

### C3. Void on a command

**C3.1** Every skill command, `/roll`, and the three knack commands accept an optional `void` count
which defaults to none.

**C3.2** The spend goes through R1's server-side operation. No void rule is reimplemented in the
command layer.

**C3.3** Refusals are **ephemeral** (only the invoker sees them) and name the number: how many
points they have, or what their per-roll cap is. Nothing is posted to the channel, no dice are
rolled, and nothing is written.

**C3.4** The activation point comes first. For `/commune`, one point is reserved via the formula's
existing `requires_void_point`, and any requested `void:k` is checked against what remains - so a
character whose cap is 3 but who holds 2 points can put exactly 1 into a Commune roll. **Leave a
comment at the point of change saying so**; this is the kind of ordering a later edit silently
inverts.

### C4. `/initiative`

**C4.1** `/initiative` calls R2's operations: roll initiative, start the round, post the result.

**C4.2** It takes **no void option**. The rules are explicit - `rules/03-combat.md`, Initiative:
"You begin each round by rolling dice equal to your Void Ring plus 1 *without spending void points*
or rerolling 10s". The GM confirmed this on 2026-09-20.

**C4.3** For a Togashi Ise Zumi, `/initiative` rolls the default variant. A slash command has
nobody to ask which variant, which is the same rule this repo already applies to the Merchant's
`/commerce`. An optional `variant` argument was considered and declined: it would show for every
player to serve one school.

### C5. Which character, and who may roll it

**C5.1** Character resolution is unchanged from `/etiquette`: the GM's `DISCORD_ROLL_CHARACTER_OVERRIDES`
pin, else the character they own that is in a gaming group, else an ephemeral explanation. Never a
guess.

**C5.2** Because these commands now WRITE, the invoker must not be able to change a character they
could not edit on the sheet itself. Resolution already returns only an owned or pinned character;
assert that with a test rather than leaving it as a property of the current implementation, so a
later change to resolution cannot quietly become a write hole.

**C5.3** Recording follows `should_record_roll` exactly as today, including the blanket admin
exclusion. A GM rolling on a pinned test character still spends that character's void - the
no-history rule is about the record, not about the dice.

**C5.4** A command for a knack the character does not have gets an ephemeral "you do not have the
Commune knack", not a generic failure. `build_all_roll_formulas` emits knack formulas only for
knacks the character holds, so this is a `None` formula rather than a new lookup.

### C6. What gets posted

| roll | posted line |
|---|---|
| plain skill | `**Name**: **31** Sincerity@3` (unchanged) |
| with void | `**Name**: **38** Sincerity@3 (1 void)` |
| commune | `**Name**: **24** Commune (Water) (1 void to activate)` |
| initiative | `**Name** rolls initiative - action dice: 2, 5, 7` |

**C6.1** The parenthesized suffix is load-bearing, not decoration. gm-assistant's roll capture
strips `(...)` spans before parsing (`webapp/l7r/repl/rolls/parse.py`, `_BREAKDOWN`), so a void
note in brackets cannot be misread as a second roll. **Please keep any spend annotation inside
parentheses**, and if the format changes, say so - gm-assistant pins these shapes with fixtures.

**C6.2** The initiative line deliberately puts no bare number immediately before a skill word, for
the same reason.

**C6.3** Initiative posts its dice card with `show_total: false`, which the renderer already
supports.

### C7. Registration

**C7.1** `scripts/register_discord_commands.py` registers the full set by default, derived per C1.1
and C1.2, with the `void` option where C3.1 says.

**C7.2** Test guild first ("Robot Role Call", instant), global afterwards (about an hour to
propagate).

### C8. What the commands do NOT do

Post-roll discretionary bonuses - raises, Lucky rerolls, Conviction points, Otherworldliness -
are applied after seeing a roll, and the GM's instruction is that the player marks those on the
sheet afterward. So no command offers them, and a command's roll must remain amendable on the sheet
in the usual way (`PATCH /characters/{id}/rolls/{roll_id}`, which already works).

---

## Part 3: requested, but NOT blocking

The GM asked that "anything that is not currently exposed over the API of the character sheet
should be updated so that it is exposed over the API". This is squarely inside that sentence and is
worth doing - but nothing in Parts 1 or 2 depends on it, because every command runs inside this app
and writes through this app's own services rather than over HTTP.

**R6.1** `GET /api/characters` should carry a character's **current** state, not only their build:
current void points (regular and temp), the current action dice, and the per-roll void cap.

Measured 2026-09-20 against the deployed app: `GET /api/characters` returns `id`, `name`,
`owner_discord_id`, `editor_discord_ids`, the gaming group, `skills` and `knacks` - no current
state of any kind. `GET /api/rolls` works and returned 200 rows for a 120-day window, so the API
itself is healthy; this is a gap in one payload, not a broken endpoint.

---

## Part 4: the general audit (the GM asked for this explicitly)

> *"what I want instead is ... the general requirement that the character sheet Claude code session
> should perform a full audit of the character sheet app to look for things such as this. which are
> purely implemented in front-end logic and which in particular would cause problems if there were
> two different browser tabs open or anything like that."*

**A1. Inventory the front-end-only rules.** Find every game rule or state transition that exists
only in browser JavaScript and has no server-side equivalent. F1 lists the ones found while
planning one feature; that search was not exhaustive and was not meant to be. Likely neighbors,
named as starting points rather than as the answer: the per-adventure reset, the night's rest,
wound-check consequences, the banked-bonus mechanisms (Matsu, Hiruma, Bayushi), spell-casting void
costs, the Priest precepts pool, the money ledger.

For each, record: what it is, where it lives, whether anything outside the browser will ever need
it, and the cost of moving it. **Moving all of it is not the goal** - genuinely presentational
logic belongs in the front end. The goal is that nobody is again surprised to find a *rule* with no
server-side existence.

**A2. Inventory the concurrency hazards.** Find every place where a client sends whole-object state
that another writer could have changed underneath it, or where two tabs on the same character can
diverge. `/track` is the one that prompted this; check the other save paths (autosave of the sheet
itself, `advantage_details`, the version/publish flow, the roll `PATCH`, the art and import jobs).
For each: can two writers lose an update, and what happens to the player when they do?

**A3. Fix the class, not the instances.** R4 is the minimum. The audit should say whether the same
mechanism covers the rest of A2, and if some path needs something different, say which and why.

**A4. Write it down.** The GM's standing rule is that a decision to accept a limitation is recorded
with the alternatives that were declined - otherwise the next session cannot tell a deliberate
choice from a bug and "fixes" it. A finding deliberately left alone is fine; a finding left alone
silently is not.

**A5. Audit fully; fix proportionately.** Every candidate in A1 and A2 gets looked at - the limit
here is on the FIXING, not on the LOOKING. Where the honest answer is "this is a genuine hazard and
fixing it is a large architectural change", say so with the measurement that establishes it and a
sketch of the fix, and leave it.

---

## Part 5: explicitly NOT wanted yet

The GM was specific. Please do not build these now; they are separate features and he will specify
them himself.

- **Otherworldliness.** It is a pre-roll bonus (raise a basic skill's rank by one, up to five, twice
  per adventure per rank) and one current player has it. Deliberately deferred: get the simple case
  working first.
- **Every other school knack and school ability.** Only the three in C1 are in scope. The rest are
  "different and not as simple as making a normal roll" and the GM will say what he wants.
- **Combat skills.** Attack, parry, iaijutsu and the rest stay out of the slash commands for now.
  `/initiative` is the one combat-adjacent command and it is the GM's own request.
- **Post-roll discretionary bonuses** (C8).
- **A write API for gm-assistant** (R5.2).

---

## Part 6: how gm-assistant will verify this

Feature 211's first task is a validation pass against the deployed app, checking behavior rather
than reading a changelog:

1. A void spend made through a command deducts from the persisted character, refuses an
   unaffordable or over-cap spend without rolling or posting, and leaves a `roll_history` row
   identical in shape to a sheet roll.
2. `/initiative` produces the same action dice the sheet would, and the sheet then shows them,
   unspent, with the previous round's state cleared and `precepts_pool` intact.
3. `/commune` charges its activation point, refuses when it cannot be paid, and checks an optional
   spend against what remains.
4. `/roll` completes skill names and refuses a hand-typed unknown skill privately.
5. The registered command set matches C1, with nothing from `COMBAT_SKILLS` reachable.
6. A stale whole-state write is rejected, and a browser tab that makes one recovers on screen
   without a reload.
7. The posted formats match C6, which gm-assistant then pins with capture fixtures.

Checked but **not blocking** - reported, never a reason to stop: R6.1, and the audit write-up.

---

## Part 7: open questions

1. **Where the concurrency token lives.** A revision counter on the character row is the obvious
   shape, but this app may prefer `updated_at`, an ETag, or field-level updates. Any of them
   satisfies R4.

2. **Whether `GET /api/characters` is the right surface for R6.1**, or whether current tracking
   state deserves its own endpoint. gm-assistant has no preference.

**Settled since the first draft**: Commune's ring. This app pins it to the character's School Ring
(`SCHOOL_RING_KNACK_IDS`); the rules text still said "the Ring of the element of the spirits you
are questioning". The GM confirmed on 2026-09-20 that the app is right and the rules text was
simply behind - *"I have been meaning to edit the commune skill to make it so that commune is
always rolled with the school ring of the person who has commune"*. So `/commune` takes no element
argument, and this app's BEHAVIOR needs no change - it is already right.

The matching edit to `rules/05-school_knacks.md` in `EliAndrewC/l7r` (`**Ring:** School Ring`, and
"roll this knack with your School Ring") has been drafted but is an **uncommitted working-tree
change** awaiting the GM's own commit, so do not treat it as published rules text yet. Nothing
above depends on it.

**One small text fix falls out of it, for this session to make**: `game_data.py`'s Commune entry
still carries `ring="varies"` and the description "Rolled with the ring of the element communed
with", which is now wrong in both places even though `SCHOOL_RING_KNACK_IDS` makes the code do the
right thing. The catalog ring is still the correct FALLBACK value for a character whose pinning
cannot resolve, so this is a wording question rather than a data change - but a description that
contradicts the rules and the code is the kind of thing that gets believed later.

---

## Notes on working with this

- gm-assistant's planning record is `specs/211-sheet-slash-commands/` in
  <https://github.com/EliAndrewC/gm-assistant>. Its `spec.md` states the same commands as user
  stories with acceptance scenarios, which may be useful as a second phrasing; `plan.md` has the
  file-and-line detail behind Part 0.
- The two sessions do **not** talk to each other. The GM judged a direct channel not worth setting
  up, and gm-assistant agrees: this is a one-way handoff of a written specification, and the
  questions that matter are the GM's, not another session's.
- This file was written into this repository's working tree but **not committed** - gm-assistant's
  session is forbidden from making git writes here. Commit it, move it, or fold it into a design
  directory as suits this repo.
