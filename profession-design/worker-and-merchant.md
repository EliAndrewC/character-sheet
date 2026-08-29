# Professions, part 3: the Worker and Merchant abilities

Status: **planning, awaiting sign-off. No code written.**
Created 2026-08-29. Follows `profession-design/design.md` (Wave Man) and
`profession-design/priest-and-pooling.md` (one Profession type, pooled
abilities, Priest rituals). Source rules: `rules/09-professions.md`.

Turns Worker and Merchant from `preview` to `available`, with one ability
held back. Most of the twenty are **conditional free raises**, which the sheet
already models as "Alternative totals" rows - so the bulk of this is data plus
one new per-ability gate, not new machinery. Three abilities do not fit that
mould and are the subject of the open questions.

Ability numbering below is **Wk1-Wk10** (Worker) and **M1-M10** (Merchant),
matching the order in `rules/09-professions.md`, and used in code comments and
test names as W1-W10 already are for the Wave Man.

---

## 1. Rulings

Everything from parts 1 and 2 carries over unless contradicted here.

| # | Ruling |
|---|---|
| R1 | **Worker and Merchant become available**, joining Wave Man and Priest in the pool. Ninja stays hidden. |
| R2 | **Wk5 ("buy and raise any advanced skill which is normally basic as if it were basic") is greyed out and not selectable**, being campaign-specific - as its own parenthetical footnote says. |
| R3 | Every other Worker and Merchant ability is selectable. |
| R4 | **Most Worker abilities will have no mechanical implementation.** There are no sickness or fatigue mechanics in this app, so those abilities are displayed and nothing more. |
| R5 | **Money bonuses accumulate into a single percentage figure** which the sheet keeps track of. |
| R6 | **Almost all of these abilities surface as conditional bonuses** - the existing "Alternative totals" system. A character who takes many of them should expect a lot of alternative rows on their rolls; that is the intended shape of the feature, not a symptom. |

---

## 2. What this rides on, and what it does not

**The conditional-bonus system is a direct fit, with one limit.** An entry in
a formula's `alternatives` list is `{label, extra_flat}`, optionally with
`open_roll` and its own `max_total`. It renders as an "Alternative totals" row
in the roll modal and as a tooltip note on the View Sheet's skill panel, and
`roll_engine.py` mirrors it for the Discord bot. Fourteen of the twenty
abilities are exactly this shape.

**But `alternatives` carries flat bonuses only.** There is no `extra_flat`
counterpart for dice: `alt_total()` in `roll_engine.py` and
`applyTotalCap`/`altTotal` in `roll_math.js` both read `extra_flat` and
nothing else. That is a real constraint rather than an oversight - an
alternative total is computed from a roll that already happened, and you
cannot retroactively add dice to it. **M10 is the one ability this blocks**
(see Q2).

**The stipend already has a modifier list.** `EffectiveStatus.stipend_modifiers`
in `app/services/status.py` is a list of `{source, detail}` entries beside a
`stipend` computed as `stipend_rank ** 2`; Household Wealth and the Merchant
school's 4th Dan already push into it. A money-bonus percentage has an obvious
home there (see Q3 for whether it should actually move the number).

**Per-ability availability is new.** `Profession.availability` is per
profession; R2 needs one ability inside an otherwise-available profession to
be greyed out. That is a small addition - `ProfessionAbility.available: bool`,
with the effective answer being `profession.is_available and ability.available`
- but it touches the sanitizer, the validator, and the editor's stepper gate,
so it is Phase 1 rather than a footnote.

---

## 3. The twenty abilities

**Conditional free raises** - a `{label, extra_flat}` alternatives row on the
named skill. Fourteen of the twenty, and the whole of Phase 2.

| id | skill(s) | raises | condition (the row's label) |
|---|---|---|---|
| Wk4 | etiquette | 3 | when speaking to someone of higher social class |
| Wk6 | commerce | 3 | when making purchases |
| Wk7 | bragging, precepts | 4 | when speaking about your own ethics |
| Wk10 | sincerity, tact | 5 | when avoiding trouble with an authority figure (**open rolls only**) |
| M1 | sincerity | 2 | relating to your business |
| M2 | interrogation | 2 | relating to your business |
| M3 | investigation | 4 | relating to your business |
| M4 | bragging, precepts | 3 (+1 more if contested) | relating to your business experience |
| M5 | commerce | 2 | contested, and your commerce rank is at least your opponent's |
| M6 | culture | 4 | to purchase gifts |
| M7 | heraldry | 5 | for knowing your customers and their families |
| M8 | law | 3 | relating to your business |

All twelve skills exist in `SKILLS`. M4 needs **two rows** (plain and
contested) rather than one, since the sheet cannot know which a given roll is.
M5's condition is unverifiable by the sheet - it names the opponent's rank -
so it is a label, exactly as Streetwise's "when invoking bounty hunter
authority" already is.

**No implementation, displayed only** (R4). Five abilities:

| id | ability | why |
|---|---|---|
| Wk1 | Regain a VP with 4 fewer hours of sleep | The app has a Night's Rest but does not model hours slept |
| Wk2 | Sickness penalties halved (a fourth if taken twice) | No sickness mechanics |
| Wk3 | Ignore one day's worth of fatigue penalties | No fatigue mechanics |
| Wk8 | 2 free raises on strength rolls | **See Q1** - there is no "strength roll" in this app or the rules |
| Wk9 | 2 free raises on all endurance rolls | **See Q1** - likewise |

Wk2 is worth noting for a different reason: "Taking this twice cuts it to a
fourth" is the rules explicitly describing a **non-linear** second copy. It is
the only ability in any profession that does, which is good evidence that the
plain doubling assumed everywhere else is the intended default - see Q4.

**Not selectable** (R2): **Wk5**, advanced-skills-as-basic.

**Neither, and the reason for the open questions:**

| id | ability | problem |
|---|---|---|
| M9 | Spend a void point to reroll any roll relating to your business | A reroll, not a bonus. Shaped like Lucky, which already exists. See Q5 |
| M10 | Roll 4 extra dice on open commerce rolls relating to your business | Extra **dice**, which `alternatives` cannot express. See Q2 |

---

## 4. Working method

Unchanged: **unit tests are TDD and live in the phase that owns the code**,
tagged `TDD:` and written failing first; clicktests are the exception and all
sit in the last phase. Every phase must leave the existing 3625 unit tests,
150 JS tests and 41 profession clicktests green, not just its own.

---

## 5. Phase 1 - per-ability availability and the data

- [ ] `TDD:` tests for per-ability availability and the new data.
- [ ] `ProfessionAbility.available: bool = True`. Effective availability is `profession.is_available and ability.available`; a single helper in `services/professions.py` so no caller re-derives it.
- [ ] `max_for_ability()` returns 0 for an unavailable ability, which makes the sanitizer drop it with no further change.
- [ ] `PROFESSION_ABILITY_POOL` and `profession_ability_pool_size()` skip unavailable abilities, so the pooled ceiling counts what can actually be taken: Wave Man 20 + Priest 10 + Worker 18 (nine abilities x2) + Merchant 20 = **68 picks**, reached at 1155 XP.
- [ ] `Profession.availability` flips to `"available"` for `worker` and `merchant`; `Wk5.available = False`.
- [ ] `implemented` is set truthfully per ability, so the editor's existing "narrative" chip lands on the five R4 abilities and Wk8/Wk9.
- [ ] `TDD:` a crafted POST naming Wk5 is dropped on write; validation names it as unavailable rather than as unknown.
- [ ] `TDD:` the pool size and the 68-pick ceiling.

## 6. Phase 2 - the fourteen conditional free raises

- [ ] `TDD:` one test per ability asserting the alternatives row (skill, `extra_flat`, label), at one and two copies.
- [ ] `PROFESSION_ALTERNATIVE_SKILL_BONUSES` in `game_data.py`: ability id -> `(skill_ids, raises, label, open_roll)`. Declarative, beside `PROFESSION_ABILITY_BONUSES`, so adding the rest of a profession later is data.
- [ ] Applied in `build_skill_formula()` where the campaign-advantage alternatives already are, multiplying `raises` by the copy count (D5).
- [ ] M4 emits **two** rows - the plain one and a larger contested one - since a single row cannot say "unless contested, in which case more".
- [ ] Wk10's rows carry `open_roll: True`, which the existing renderer already honours.
- [ ] Two abilities can land on one skill with different conditions (Wk7 and M4 both touch bragging); they must produce **two separate rows**, not a merged one. Assert it.
- [ ] `TDD:` `tests/test_roll_engine.py` case confirming the bot's card shows the new alternatives, since `_alternatives_for_payload` picks them up for free.
- [ ] Check the interaction with `_finalize_caps` and Withdrawn's `max_total`: an alternative that lifts an open sincerity roll must still respect the cap.

## 7. Phase 3 - the money bonus

- [ ] `TDD:` accumulation tests, including two copies of an ability doubling its bonus and Wk5 (unavailable) contributing nothing.
- [ ] `profession_money_bonus(character_data) -> int` in `services/professions.py`: the summed percentage over held abilities, counting each copy.
- [ ] Surfaced as a single figure on the View Sheet, next to the stipend where the other money information already lives.
- [ ] Whether it actually multiplies the stipend, or is displayed for the GM to apply, is **Q3**. If it multiplies, it becomes a `stipend_modifiers` entry so its provenance shows in the existing tooltip.
- [ ] Include it in the Google Sheets export and `GET /api/characters` if it moves the number; skip both if it is display-only.

## 8. Phase 4 - M9 and M10

Contents depend on Q2 and Q5. Placeholder items for the likely shapes:

- [ ] M10: whichever of a pre-roll "relates to my business" toggle, an extension to `alternatives`, or reference text Q2 settles on.
- [ ] M9: whichever of a void-spend reroll button (mirroring Lucky's) or reference text Q5 settles on.
- [ ] If either lands as reference text, it still needs its "tell your GM" note, and `implemented` stays false so the editor's narrative chip is accurate.

## 9. Phase 5 - display

- [ ] The editor greys out Wk5 individually inside an otherwise-live Worker block, with its own "not available in this campaign" note rather than the profession-level one.
- [ ] Money bonuses are already carried on `ProfessionAbility.money_bonus` and are shown nowhere; surface each ability's own figure in the editor row so a player can see what they are buying.
- [ ] The View Sheet's profession panel keeps showing only taken abilities, now with money bonuses and the "tell your GM" note on the narrative ones.
- [ ] `TDD:` render tests for the individually-greyed ability and the money figures.
- [ ] Rerun `scripts/build-css.sh`.

## 10. Phase 6 - clicktests, coverage and docs

- [ ] Clicktest: Worker and Merchant blocks are live (not the greyed preview they were), and Wk5 alone is disabled inside Worker.
- [ ] Clicktest: taking Wk4 puts an "Alternative totals" row on an etiquette roll with the right number, and taking it twice doubles it.
- [ ] Clicktest: a character holding Wk7 and M4 sees two distinct bragging rows.
- [ ] Clicktest: the accumulated money bonus renders on the sheet.
- [ ] Clicktest for whatever Q2 and Q5 produce.
- [ ] Add a Worker/Merchant character to the `test_sheet_js_errors.py` sweep.
- [ ] Coverage back to 100%; `COVERAGE.md`; `school-features/` docs for the two new ability sets; the Professions section of `CLAUDE.md`.
- [ ] Deploy.

---

## 11. Open questions

**Q1 - what is a "strength roll" and an "endurance roll"?** (Wk8, Wk9.)
Neither exists as a skill in this app, and grepping `rules/` finds no such
roll type either - the only hits for "strength" are about the strength of
one's convictions. Candidates: athletics rolls with a particular Ring (the
sheet rolls athletics per Ring), raw Ring rolls (Earth for endurance seems
natural), or something the GM adjudicates with no fixed formula. If they are
Ring or athletics rolls I can implement both as conditional bonuses in Phase
2; if they are GM-adjudicated they join the narrative group. **This is the
only question that changes the phase-2 scope.**

**Q2 - M10 rolls 4 extra dice, which the alternatives system cannot express.**
An alternative total is derived from dice already rolled, so extra dice cannot
be offered after the fact. Three options:

  (a) **A pre-roll toggle** in the roll menu - "this commerce roll relates to
      my business" - that adds the dice before rolling, the way the attack
      modal's Doji "untouched target" checkbox already works. Correct
      behaviour, and a new control on the generic roll menu, which currently
      only offers void spending.
  (b) **Extend `alternatives` to carry dice.** I would rather not: every
      consumer (`roll_math.js`, `roll_engine.py`, the modal, the dice card)
      assumes an alternative is arithmetic on a finished total, and a row that
      cannot state its number would be a worse lie than no row.
  (c) **Reference text**, like the Wave Man's opponent-facing abilities.

**Q3 - does the accumulated money bonus change the stipend, or only display?**
The stipend is `rank ** 2` with a modifier list that Household Wealth and the
Merchant school already push into, so multiplying it is easy and would show
its provenance in the existing tooltip. But the rules head the Worker list
with "Money bonuses may or may not apply depending on the campaign", so
whether it should touch the number at all is yours. Display-only is also fine
and is the smaller change.

**Q4 - do free raises double when an ability is taken twice?** The standing
rule (part 1, D5) is that N copies apply the effect N times, which for these
means Wk10 at two copies giving **ten** free raises, or +50 on a roll.
Confirming because these numbers get large, and because Wk2's "taking this
twice cuts it to a fourth" is the rules bothering to specify a non-linear
second copy - which reads as evidence that linear is the default everywhere
else, but is worth saying out loud before I bake +50 into a roll.

**Q5 - is M9 worth implementing?** "Spend one void point to reroll any roll
relating to your business" is shaped exactly like the Lucky advantage's
reroll, which already exists, so the button is cheap. The condition is
GM-adjudicated, and it spends a void point the sheet does track. Implement it
as a reroll button on qualifying rolls, or leave it as reference text?

**Q6 - which rolls count as "relating to your business"?** Seven Merchant
abilities carry that condition and I am treating it purely as label text the
player reads before deciding whether the alternative applies - the same way
Streetwise's condition works today. Flagging only to confirm you do not want
the sheet trying to decide it (for instance by having the player record a
business on their sheet).
