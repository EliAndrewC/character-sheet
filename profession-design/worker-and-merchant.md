# Professions, part 3: the Worker and Merchant abilities

Status: **planning complete, awaiting sign-off. No code written.**

Every rules question raised during planning has been answered by the GM and is
recorded in section 1. There is no open-questions section.
Created 2026-08-29. Follows `profession-design/design.md` (Wave Man) and
`profession-design/priest-and-pooling.md` (one Profession type, pooled
abilities, Priest rituals). Source rules: `rules/09-professions.md`.

Turns Worker and Merchant from `preview` to `available`, with one ability held
back. Fourteen of the twenty are **conditional free raises**, which the sheet
already models as "Alternative totals" rows - so the bulk of this is data plus
one new per-ability gate. Two need new interaction (a pre-roll menu variant and
a reroll button), three have no mechanics at all, and one is not selectable.

Ability numbering is **Wk1-Wk10** (Worker) and **M1-M10** (Merchant), matching
the order in `rules/09-professions.md`, and used in code comments and test
names as W1-W10 already are for the Wave Man.

---

## 1. Rulings

Everything from parts 1 and 2 carries over unless contradicted here.

| # | Ruling |
|---|---|
| R1 | **Worker and Merchant become available**, joining Wave Man and Priest in the pool. Ninja stays hidden. |
| R2 | **Wk5 ("buy and raise any advanced skill which is normally basic as if it were basic") is greyed out and not selectable**, being campaign-specific - as its own parenthetical says. |
| R3 | Every other Worker and Merchant ability is selectable. |
| R4 | **Several Worker abilities have no mechanical implementation.** There are no sickness or fatigue mechanics in this app, so those abilities are displayed and nothing more. |
| R5 | **Money bonuses accumulate into a single percentage figure** the sheet keeps track of. |
| R6 | **Almost all of these abilities surface as conditional bonuses** - the existing "Alternative totals" system. A character who takes many of them should expect a lot of alternative rows; that is the intended shape, not a symptom. |
| R7 | **Wk8 and Wk9 are athletics rolls**, Water for feats of strength and Earth for feats of endurance. The rules were reworded upstream to say so, along with three other tweaks - see section 2. |
| R8 | **M10 is chosen before the roll, not after.** The commerce tile offers "roll commerce" and "roll open commerce relating to your business" as separate options, each with its own void-spend submenu, exactly as a Ring tile offers "Roll Air" and "Roll Air athletics". Once chosen there is no conditionality left. |
| R9 | **The money bonus multiplies the stipend**, applied after every other stipend modifier. |
| R10 | **All bonuses double when an ability is taken twice**, free raises included. |
| R11 | **M9 is implemented as a reroll button.** |
| R12 | **"Relating to your business" is label text**, judged by the player, exactly like the Streetwise advantage's condition. The sheet does not try to decide it. |
| R13 | **M9's reroll is offered on all 18 skill rolls**, being the one Merchant ability that names no skill ("reroll *any* roll relating to your business"). The free-raise abilities stay on the skills they each name. |

---

## 2. Pull the reworded rules text first

The GM reworded five abilities upstream. Diffing the stored text against
`rules/09-professions.md` finds **exactly these five, all in Worker and
Merchant**; Wave Man, Priest and Ninja are clean.

| id | change |
|---|---|
| Wk5 | Parenthetical gains: "If you take this ability after having already spent XP on an advanced skill, you get back the extra XPs which were previously spent." |
| Wk8 | "2 free raises on strength rolls" becomes **"2 free raises when making Water athletics rolls for feats of strength"** |
| Wk9 | "2 free raises on all endurance rolls" becomes **"2 free raises when making Earth athletics rolls for feats of endurance"** |
| M5 | "when your commerce **rank**" becomes "when your commerce **skill**" |
| M6 | "to culture rolls **to purchase gifts**" becomes "for the purpose of purchasing gifts" |

Wk8 and Wk9 are the substantive ones: they turn two abilities that named a
roll type this app does not have into two that ride `build_athletics_formula`,
which already builds `athletics:Water` and `athletics:Earth`. They move out of
the narrative group and into Phase 2.

Wk5's new clause describes an XP refund. It stays unimplemented under R2, but
the text should be current so the greyed-out entry reads correctly.

- [ ] `TDD:` a test that asserts every stored ability's text matches
      `rules/09-professions.md` verbatim, parsing the markdown at test time.
      This drift has now happened twice (W3 during part 1, five more here) and
      a test is cheaper than noticing by eye a third time.

---

## 3. What this rides on

**The conditional-bonus system is a direct fit.** An entry in a formula's
`alternatives` list is `{label, extra_flat}`, optionally with `open_roll` and
its own `max_total`. It renders as an "Alternative totals" row in the roll
modal, as a tooltip note on the View Sheet's skill panel, and on the Discord
bot's card via `_alternatives_for_payload`. Fourteen of the twenty abilities
are exactly this shape once R7 moves Wk8/Wk9 in - six Worker and eight
Merchant.

**The roll menu already does pre-roll variants.** `roll_trigger.html` renders
a picker block whose every row carries a hover void-spend submenu, gated by
`rollMenuHasAthleticsPicker`, and `executeRoll('athletics:' + ring, count, opt)`
runs the chosen one. R8 is that pattern with a different key, so M10 is a new
formula key plus a menu row - not new machinery.

**The stipend already has a modifier list.** `EffectiveStatus.stipend_modifiers`
is a list of `{source, detail}` beside a `stipend` of `stipend_rank ** 2`;
Household Wealth and the Merchant school's 4th Dan already push into it. R9
lands as a final multiplier with its own entry, so its provenance shows in the
existing tooltip.

**Per-ability availability is new.** `Profession.availability` is per
profession; R2 needs one ability inside an otherwise-available profession
greyed out. Small - `ProfessionAbility.available: bool` - but it touches the
sanitizer, the validator and the editor's stepper gate.

---

## 4. The twenty abilities

**Conditional free raises**, a `{label, extra_flat}` row on the named roll.
Fourteen abilities, and the whole of Phase 2. Raise counts double at two copies
(R10).

| id | roll(s) | raises | condition (the row's label) |
|---|---|---|---|
| Wk4 | etiquette | 3 | when speaking to someone of higher social class |
| Wk6 | commerce | 3 | when making purchases |
| Wk7 | bragging, precepts | 4 | when speaking about your own ethics |
| Wk8 | **athletics:Water** | 2 | for feats of strength |
| Wk9 | **athletics:Earth** | 2 | for feats of endurance |
| Wk10 | sincerity, tact | 5 | when avoiding trouble with an authority figure (**open rolls only**) |
| M1 | sincerity | 2 | relating to your business |
| M2 | interrogation | 2 | relating to your business |
| M3 | investigation | 4 | relating to your business |
| M4 | bragging, precepts | 3, or 4 if contested | relating to your business experience |
| M5 | commerce | 2 | contested, and your commerce skill is at least your opponent's |
| M6 | culture | 4 | for the purpose of purchasing gifts |
| M7 | heraldry | 5 | for knowing your customers and their families |
| M8 | law | 3 | relating to your business |

M4 needs **two rows**, plain and contested, since one row cannot say "unless
contested, in which case more". M5's condition names the opponent's commerce
skill, which the sheet cannot know, so it is label text - exactly as
Streetwise's condition already is (R12).

**New interaction**, two abilities:

| id | shape |
|---|---|
| M10 | A second roll option on the commerce tile - "open commerce relating to your business", 4 extra rolled dice - with its own void-spend submenu (R8) |
| M9 | A reroll button, spending a void point, on rolls relating to your business (R11) |

**No implementation, displayed only** (R4): **Wk1** (VP on less sleep - the
app has a Night's Rest but does not model hours slept), **Wk2** (sickness),
**Wk3** (fatigue). Wk2 is worth noting for a different reason: "Taking this
twice cuts it to a fourth" is the rules explicitly describing a **non-linear**
second copy, and the only ability in any profession that does - which is why
R10's plain doubling everywhere else is safe to assume.

**Not selectable** (R2): **Wk5**.

---

## 5. Working method

Unchanged: **unit tests are TDD and live in the phase that owns the code**,
tagged `TDD:` and written failing first; clicktests are the exception and all
sit in the last phase. Every phase must leave the existing 3625 unit tests,
150 JS tests and 41 profession clicktests green, not just its own.

---

## 6. Phase 1 - rules text, per-ability availability, data

- [ ] `TDD:` the rules-text drift test described in section 2.
- [ ] Pull the five reworded texts.
- [ ] `TDD:` tests for per-ability availability.
- [ ] `ProfessionAbility.available: bool = True`. Effective availability is `profession.is_available and ability.available`, behind one helper in `services/professions.py` so no caller re-derives it.
- [ ] `max_for_ability()` returns 0 for an unavailable ability, which makes the sanitizer drop it with no further change.
- [ ] `PROFESSION_ABILITY_POOL` and `profession_ability_pool_size()` skip unavailable abilities, so the ceiling counts what can be taken: Wave Man 20 + Priest 10 + Worker 18 (nine abilities x2) + Merchant 20 = **68 picks**, reached at 1155 XP.
- [ ] `worker` and `merchant` flip to `availability="available"`; `Wk5.available = False`.
- [ ] `implemented` set truthfully per ability, so the editor's existing "narrative" chip lands on Wk1/Wk2/Wk3 and nothing else.
- [ ] `TDD:` a crafted POST naming Wk5 is dropped on write, and validation calls it unavailable rather than unknown.
- [ ] `TDD:` the pool size and the 68-pick ceiling.

## 7. Phase 2 - the fourteen conditional free raises

- [ ] `TDD:` one test per ability asserting the alternatives row (roll key, `extra_flat`, label), at one and two copies.
- [ ] `PROFESSION_ALTERNATIVE_BONUSES` in `game_data.py`: ability id -> `(roll_keys, raises, label, open_roll)`. Declarative, beside `PROFESSION_ABILITY_BONUSES`, so a future profession is data.
- [ ] Applied in `build_skill_formula()` where the campaign-advantage alternatives already are, multiplying `raises` by the copy count (R10).
- [ ] **Also applied in `build_athletics_formula()`**, which Wk8/Wk9 need and which no profession ability has touched before. Confirm alternatives survive the dice-cap step there the way they do for skills.
- [ ] M4 emits two rows, plain and contested.
- [ ] Wk10's rows carry `open_roll: True`, which the renderer already honours.
- [ ] Two abilities landing on one roll with different conditions (Wk7 and M4 both touch bragging) must produce **two separate rows**, not a merged one. Assert it.
- [ ] Interaction with `_finalize_caps` and Withdrawn's `max_total`: an alternative lifting an open sincerity roll must still respect the cap.
- [ ] `TDD:` `tests/test_roll_engine.py` case confirming the bot's card shows the new alternatives.

## 8. Phase 3 - M10, the pre-roll commerce variant

- [ ] `TDD:` the new formula key exists only for a character holding M10, and carries 4 extra rolled dice over plain commerce, doubling to 8 at two copies.
- [ ] New key `skill:commerce:business` from `build_all_roll_formulas`, built from the commerce formula with the extra dice added before `apply_dice_caps`.
- [ ] A picker block on the commerce tile mirroring `rollMenuHasAthleticsPicker`: two rows, each with the existing hover void-spend submenu. Prefer a **generic** `roll_variants` list on the formula over a commerce-specific flag, so the next profession that needs one is data.
- [ ] The variant is an *open* roll by the ability's own wording; make sure nothing that keys on open-vs-contested (Withdrawn's cap, the sincerity honor bonus) is confused by the new key.
- [ ] `roll_engine.py` reaches it for free once the key exists, but the slash commands map command names to `skill:<id>` - decide whether `/commerce` should offer the variant or stay the plain roll. Leaning plain: a slash command has nobody to ask which it is.
- [ ] `TDD:` a school character and a profession character without M10 get no such key.

## 9. Phase 4 - M9, the business reroll

- [ ] `TDD:` the flag appears only for a holder, and the reroll spends exactly one void point.
- [ ] A reroll button on qualifying roll results, modelled on the Lucky reroll that already exists (`luckyUsedThisRoll` and its banner), spending one void point rather than consuming Lucky.
- [ ] Once per roll, like Lucky - and it must interact correctly with Lucky and with the PCP reroll, none of which may double up on one roll. Assert the combinations.
- [ ] **Read-only Roll Mode:** a non-editor may walk the reroll and see the new total, but the void point must not be deducted. Gate the spend on `t.canEdit` per the standing rule.
- [ ] Offered on **all 18 skill rolls** (R13) - M9 is the only Merchant ability that names no skill, so unlike the free raises it is not tied to one. Whether it should also reach non-skill rolls (rings, athletics, combat) is not something the rules text settles; "any roll relating to your business" reads as any roll, but every other Merchant ability is a skill ability, so the plan scopes it to skills and leaves widening it as a later data change.
- [ ] `TDD:` the button offers on every skill and on no skill for a character without M9.

## 10. Phase 5 - the money bonus

- [ ] `TDD:` accumulation, including two copies doubling a bonus and Wk5 contributing nothing.
- [ ] `profession_money_bonus(character_data) -> int` in `services/professions.py`: the summed percentage over held abilities, counting each copy (R10).
- [ ] Applied in `compute_effective_status` as a **final multiplier** on the stipend, after every other modifier (R9), with its own `stipend_modifiers` entry naming the percentage so the existing tooltip explains it.
- [ ] Rounding: `int()` truncation matches how the stipend is already computed; state it in the modifier's detail text so a player can reconcile the number.
- [ ] `TDD:` a Merchant with several abilities gets the right stipend, and the modifier list reads in the right order.
- [ ] Surfaced on the View Sheet beside the stipend, in the Google Sheets export, and in `GET /api/characters`.

## 11. Phase 6 - display

- [ ] The editor greys out Wk5 individually inside an otherwise-live Worker block, with its own "not available in this campaign" note rather than the profession-level one.
- [ ] Each ability's own money bonus is shown in its editor row - the data is already on `ProfessionAbility.money_bonus` and rendered nowhere.
- [ ] The View Sheet's profession panel keeps showing only taken abilities, now with money bonuses and the "tell your GM" note on the narrative ones.
- [ ] `TDD:` render tests for the individually-greyed ability and the money figures.
- [ ] Rerun `scripts/build-css.sh`.

## 12. Phase 7 - clicktests, coverage and docs

- [ ] Clicktest: Worker and Merchant blocks are live, and Wk5 alone is disabled inside Worker.
- [ ] Clicktest: taking Wk4 puts an "Alternative totals" row on an etiquette roll with the right number; taking it twice doubles it.
- [ ] Clicktest: a character holding Wk7 and M4 sees two distinct bragging rows.
- [ ] Clicktest: Wk8 puts a row on a Water athletics roll and not on an Earth one.
- [ ] Clicktest: the commerce tile offers both roll options, each with a void submenu, and the business one rolls 4 more dice.
- [ ] Clicktest: the M9 reroll button spends a void point and rerolls; a non-editor's void count does not move.
- [ ] Clicktest: the accumulated money bonus renders on the sheet and the stipend reflects it.
- [ ] Add a Worker/Merchant character to the `test_sheet_js_errors.py` sweep.
- [ ] Coverage back to 100%; `COVERAGE.md`; `school-features/` docs for the two new ability sets; the Professions section of `CLAUDE.md`.
- [ ] Deploy.
