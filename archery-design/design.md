# Archery Attacks - Design

Status: **draft, waiting on the GM's answers to section 4** (2026-10-17). Nothing is built yet.
Each question has a proposed default, so the phases those answers don't affect can start now.

Source: `rules/03-combat.md` "Archery Rules" (TN to be hit, Parrying arrows, Moving while under fire).

## 1. Goal

Add an **Archery Attack** that any character can make from an action die, the way they make an
ordinary attack today. Every rule from the rules section should be applied by the server, and the
modal should expose every input the rules need:

- the TN built from its parts (parry or unseen, distance, evasion, cover);
- the bonus for holding actions, which resets with each arrow;
- extra actions spent in the same phase;
- the iaijutsu bonus;
- every attack and damage bonus from every attack type, stacked;
- damage drawn from the weighted 10kN table, shifted by how far the roll beat the TN;
- the automatic serious wounds, and what a failed parry takes away.

## 2. The rules, as implemented

### 2.1 The attack roll

- Rolled with the **attack** skill: (attack + Fire)k(Fire), like a plain attack.
- **All bonuses to attack rolls, for all attack types, stack.** This means 1st Dan dice and 2nd Dan
  raises keyed to `attack`, `double_attack`, `counterattack`, `lunge` and `iaijutsu`.
  - The rules' own example is the acceptance test: a Kakita at 4th Dan gets **+2k0 +5** on the
    arrow: 1st Dan's +1k0 for iaijutsu and +1k0 for double attack, plus 2nd Dan's +5 for iaijutsu.
    Their damage also gets **+5**, from the 4th Dan technique that normally applies only to iaijutsu.
- **Hold bonus:** +1 per phase the action was held, counted from whichever is later: the die's value
  or the phase the last arrow was fired this round.
  - `bonus = phase - max(die_value, last_arrow_phase)`, never below 0.
  - Example from the rules: dice 1 and 2, fire in phase 5, get +4. A second arrow in phase 5 gets +0.
- **Extra actions:** any number of other unspent dice that have come up by the current phase
  (value <= phase) may be spent too. Each gives **+5**, plus its own hold bonus (see Q1).
- **Iaijutsu:** +(iaijutsu knack rank), flat, if the character has the knack.
- Void, 10s and Impaired work as for the ordinary attack. It is a skill roll, so Discordant blocks
  void and Impaired stops 10s from rerolling. It is a combat roll, so Mirumoto 5th Dan applies.

### 2.2 TN to be hit

| part | value |
|---|---|
| base, target can see the arrow | 5 + 5 x parry |
| base, target cannot see it | 5 (not 0, unlike melee) |
| distance 0-49 / 50-99 / 100-199 / 200-399 ft | +5 / +10 / +15 / +20 |
| 400+ ft | out of range; the modal does not offer it |
| target spent an action on **evasion** this round | +5 |
| partial **cover** | +N, as the GM says (typically 10-30) |

Full cover makes a hit impossible. That is the GM saying "you can't", not an input.

### 2.3 Damage

- An arrow does no ordinary damage dice: there is no weapon, no ring and no extra dice for beating
  the TN. Damage is **one table roll**:

  | 10k2 | 10k4 | 10k6 | 10k8 |
  |---|---|---|---|
  | 30% | 30% | 30% | 10% |

- **Each full 5 the attack beat its TN by moves 10%** from the lowest band that still has any to
  10k8. Nine shifts (an excess of 45) make 10k8 certain. After that, **each further full 5 is a free
  raise (+5)** on the damage roll: `raises = max(0, excess // 5 - 9)`.
  - Excess 12: 10 / 30 / 30 / 30. Excess 22: 0 / 20 / 30 / 50. Excess 50: 10k8 + 5.
- The bands are whole tenths, so **the band is picked with one d10** (low numbers pick the lowest
  band). The roll is real, can be forced in tests, and is shown on the card.
- **Automatic serious wounds:** 1 for the arrow, plus 1 more if the archer has the **double attack**
  knack. That extra one has no effect on the TN.
- **Parry:** the parry's TN is the attack's total, as usual.
  - A **successful** parry negates the whole attack.
  - A **failed** parry removes only the arrow's own serious wound. It does not remove double
    attack's serious wound, change the band odds, or take away any dice.

## 3. Decisions (proposed; confirmed ones move to "GM" in the last column)

| # | decision | why |
|---|---|---|
| A1 | **One roll key, `archery`**, an attack type (`is_attack_type`, `attack_variant: "archery"`); its damage is recorded as `archery:damage`. | Every consumer that is decided by key (`is_combat_roll`, `_discordant_blocks_void`, `skill_rank_for_roll`'s `_ATTACK_ROLL_KEYS`, `is_wave_man_attack_key`, `_annotate_third_dan`, the fight log, roll descriptions, card titles) gets `archery` added explicitly. `attack:archery` would not have helped: `_annotate_third_dan` matches only the part after the colon. |
| A2 | **The archery mode lives in the existing attack modal**, not in a new modal file, alongside `atkIsDoubleAttack()` / `atkIsAthleticsAttack()`: `atkIsArchery()` swaps the pre-roll inputs and the damage panel. | You asked for "a new type of attack modal", and the inputs and damage are new. But the roughly 40 post-roll blocks (Conviction, Lucky, PCP, Hida reroll, Akodo / Bayushi / Mirumoto banks, Priest pools, Wave Man W1, ...) must all reach arrows. A second modal would duplicate every one of them, and CLAUDE.md says the same about the combat page. |
| A3 | **The formula is built once, on the server**, by `build_archery_formula`. It starts from `build_combat_formula("attack")`, then applies `_apply_school_technique_bonus` again for `double_attack`, `counterattack`, `lunge` and `iaijutsu`, which also picks up the flexible 1st / 2nd Dan picks (Kitsune, Ide, Isawa Ishi, Priest, Mantis 2nd) when one of those is the chosen key. Then it adds the iaijutsu rank as a flat. | One place for stacking, which is the rule most likely to be wrong. |
| A4 | **Damage reuses the `damage` action**, with a branch for `attack_variant == "archery"` that calls a new `combat_math.arrow_damage()` instead of `damage_pool()`. | `_once`, PCP reroll damage, Conviction on damage, the Priest pool and `fight_log.record_act` all depend on the action being named `damage`. |
| A5 | **The TN is assembled on the server from its parts** (`base_tn` or `unseen`, `distance`, `evasion`, `cover`), and the card lists each part. The modal mirrors the sum only to draw its probability table, and both sides are pinned to `tests/shared/archery_cases.json`. | The same pattern as the attack modal today. The hit is judged on the server. |
| A6 | **Hold and extra-action bonuses are computed on the server** from the die indices and the phase the modal sends (the player picks the current phase, as Shinjo's input does). The server checks every extra die: unspent, not athletics-only, value <= phase. A live roll spends them and sets `archery_last_arrow_phase`, which joins `PER_ROUND_STATE_KEYS` so new initiative clears it. | These dice set the bonus, so the server cannot take the browser's word for them. A simulated (non-editor) roll changes nothing. |
| A7 | **"Moving while firing"**: a modal checkbox drops the hold bonus. Any other penalty for being in motion is the existing pre-roll "Extra bonus" with a negative amount. | The rules leave it to the GM. These are the two knobs the rules name. |
| A8 | **Offered to every character** with attack >= 1: "Archery Attack" on every action die that is not athletics-only, and an **Archery** row under Attack in Combat Skills (formula, roll menu and statistics badge). No bow is tracked. | The rules give no prerequisite. See Q7. |
| A9 | **The serious wounds ride the damage answer** (`serious_wounds: 1 or 2`, and `failed_parry` removes 1). The card reads "10k6 (table roll 7, 30%) - 23 light wounds + 2 serious wounds". **Nothing is written to the target**, as with every other attack: the defender enters their own wounds. | The same as CLAUDE.md's rule for NPC attacks. |
| A10 | **The damage odds are shown before the damage roll**: the hit panel lists the shifted band table for this excess (from the server's attack answer), plus any raises past 45. | The variance is the point of the rules, so the player should see it. |
| A11 | **Not modelled for arrows** (section 7): anything that changes a damage dice count from a weapon / ring / excess pool, or depends on double attack's +20 TN. | An arrow has no such pool and no +20. |

## 4. Questions for the GM (each has a proposed default)

1. **Extra actions' hold bonus.** Does each extra die count its hold from the last arrow's phase too?
   With dice 1 and 2 both spent on one arrow in phase 5, is it +4 (first die) + 5 + 3 (second die's
   +5 and its hold) = **+12**? *Default: yes, the same formula for every die.*
2. **Shinjo Special** (+2 per phase held) on top of the archery hold (+1 per phase). *Default: both
   apply ("all types of bonuses stack"), so a Shinjo arrow gets +3 per phase held.*
3. **Rolled-dice damage bonuses on a 10kN roll** (Yogo / Kuni / Brotherhood 1st Dan +1 rolled die,
   Bayushi Special +1k1 per void point spent on the attack). *Default: they apply, and the existing
   10k10 rule turns rolled dice above 10 into kept dice (10k2 + 1 rolled = 10k3). Lunge's own +1
   damage die is a knack mechanic, not a bonus, and does not apply.*
4. **Lunge-keyed 1st Dan dice** (Isawa Duelist, Otaku). The rules' list of knacks that help leaves
   lunge out. *Default: they stack, because "all types of attacks".*
5. **Hida 3rd Dan reroll count on an arrow**: X (any attack) or 2X (counterattack)? *Default: 2X,
   by the same stacking reading. Flag it if that's too generous.*
6. **Excluded as meaningless for an arrow.** *Default: all three are left out.*
   - Matsu 4th Dan's near miss, which is tied to double attack's +20 TN.
   - Otaku 5th Dan's 10-dice trade, since an arrow has no dice pool.
   - Hida 5th Dan's counterattack excess bank, which is an outcome, not a roll bonus.
7. **Who can shoot:** everyone, or only characters marked as carrying a bow (a new checkbox)?
   *Default: everyone, because the rules name no prerequisite.*
8. **The double attack serious wound** is "automatic" whenever the archer has the knack, with no
   toggle and no rank requirement beyond 1. *Default: yes.*

## 5. What exists today (and is reused)

- `dice.build_combat_formula` / `_annotate_attack_type`: the attack formula and its damage metadata
  (`damage_flat_bonus`, `damage_extra_rolled/kept`, `damage_bonus_sources`).
- `attack_rolls.build_attack`: the modal's situational inputs as named `bonuses`. It is extended
  with an archery branch: TN parts, hold, extra dice, moving.
- `attack_rolls.attack_outcome`: the double attack's +20 path does not fire for `archery`, and the
  excess it reports drives the band shifts.
- `roll_sessions`: `_start_attack`, `_after_attack_roll`, every attack-only action, `_damage`.
- `combat_math`: `apply_dice_cap`, `wave_man_round_damage` (W4 applies to arrow damage),
  Shosuro 5th Dan's lowest three dice (applies to arrow damage).
- The attack modal: initiative warnings, Target picker (`combatTargets` gives the NPC's base TN, and
  the archery parts are added to it), extra bonus, void stepper, probability table, every post-roll
  block, damage result.
- `fight_log`: records the NPC archer's attack row and its damage. It is extended to record the
  serious wounds.

## 6. Architecture

### 6.1 Formula (`dice.py`)

- `build_archery_formula(character_data)`: section 3 A3. Label `Archery (Fire)`.
- `_annotate_attack_type` gives it damage metadata with **only the flat damage bonuses**
  (Courtier +Air, the 2nd Dan damage picks, Mantis 2nd, Kakita 4th Dan +5), plus the rolled-die
  sources if Q3 is yes. `damage_ring_*` and the weapon defaults are not used.
- 3rd Dan adventure raises: `archery` is applicable when any of attack / double_attack /
  counterattack / lunge / iaijutsu is in the school's `applicable_to`, with that school's per-roll cap.
- `archery` joins `is_combat_roll`, `_discordant_blocks_void`, the Hida 3rd Dan Impaired exemption
  (via `is_attack_type`, already), `is_wave_man_attack_key`, and `_ATTACK_ROLL_KEYS` in
  `rolls_history.py`.
- New formula fields: `archery_iaijutsu_bonus`, `archery_double_attack_sw` (0 / 1).

### 6.2 Pure arithmetic (`combat_math.py`, new functions)

- `archery_tn(base_tn, unseen, distance_band, evasion, cover) -> {tn, parts}`
- `archery_hold_bonus(die_value, phase, last_arrow_phase, moving) -> int`
- `arrow_damage_bands(excess) -> {odds: [p2, p4, p6, p8] (tenths), raises}`
- `arrow_band_for_d10(odds, d10) -> kept` (10k2 / 4 / 6 / 8)
- `arrow_damage(formula, excess, d10, failed_parry, flags) -> {rolled: 10, kept, flat, raises,
  serious_wounds, parts, band_odds, d10}`, followed by `apply_dice_cap` (Q3).

### 6.3 Roll session (`attack_rolls.py`, `roll_sessions.py`)

- **Choices:** `build_attack` reads `archery: {base_tn | unseen, distance, evasion, cover,
  phase, die_index, extra_die_indices, moving}`.
  - It writes named bonuses: `held 4 phases`, `2 extra actions (+10, held +3)`, `iaijutsu +3`.
  - It sets `attack_tn` from `archery_tn`.
  - Bad input is a `ValueError`, and the roll is refused (S6).
- **After the roll:** a live roll spends the extra dice and sets `archery_last_arrow_phase = phase`.
  The primary die is spent on the path it uses today. Before writing this, check whether that is the
  client's `_preSpentDieIndex` or the server, and put the extra dice on the same path.
- **The attack answer:** `attack.archery = {tn_parts, band_odds, raises}`, so the hit panel can show
  A10.
- **`damage` action:** the archery branch draws the d10 from the session's rng, which is forceable
  with `X-Test-Dice`, then rolls `10kN`.
  - Its payload carries `serious_wounds`, `band`, `band_odds` and `d10`.
  - The `failed_parry` argument lowers the serious wounds; there is no `parry_skill` argument.
  - Weapon args are ignored.

### 6.4 Sheet UI (`modal_attack.html`, `_dice_js.html`, `action_die_menu.html`, `combat_skills.html`)

**Before the roll** (archery mode):
- Target picker.
- "Target's parry", or "Can't see the arrow" (base TN 5).
- Distance: 0-49 / 50-99 / 100-199 / 200-399 ft.
- "Target is evading (+5)".
- Cover: a +N number field.
- The resulting TN, with each part listed.
- Current phase (dropdown limited to phases at or after the die's value), with the hold bonus shown.
- A checkbox for each extra die available in this phase (value and its +5 plus hold).
- "Moving while firing (no hold bonus)".
- Iaijutsu bonus line.
- The weapon inputs are hidden.
- Probability table and void stepper, unchanged.

**Hit:**
- The shifted band table and any raises past 45.
- "Target parried and failed" checkbox (it removes 1 serious wound; no parry skill is asked for).
- The serious wounds the hit will deal.

**Damage result:**
- The band, the d10 that picked it and its odds; the dice; the light wounds; the serious wounds.
- If the target could not see the arrow: "The target may not parry, or spend void or other
  discretionary bonuses on the wound check."

**The rest:**
- Read-only mode as for every roll: the server simulates and nothing changes on the sheet.
- Dark mode, phone width, and `scripts/build-css.sh` after the class changes.

### 6.5 Cards, history, combat page, statistics

- Dice card / history titles: "Archery Attack", "Arrow Damage". `/api/rolls` passes it through
  (`skill_rank` = attack).
- The fight log records an NPC archer's attack and damage, including the serious wounds. The combat
  page's NPC roll overlay gets it for free, because it is the sheet's own modal.
- Roll statistics: the Archery row's badge and chart use the base formula. Hold, extra actions and
  TN parts are situational, so they appear as notes, like P3 in `probability-design/design.md`.
- Discord: none. Combat is excluded from the commands by construction.

## 7. What carries over to arrows

**Applied** (all of them stack):

| category | sources |
|---|---|
| 1st / 2nd Dan dice and raises on any attack type | Akodo, Bayushi, Daidoji, Hida, Isawa Duelist, Kakita, Matsu, Mirumoto, Otaku, Shiba, Yogo, Brotherhood, Ikoma, Shosuro, Doji (counterattack), and the flexible picks |
| always-on attack bonuses | Kitsuki +2 x Water, Courtier +Air (and 5th Dan), Shosuro acting dice |
| situational | Kakita 3rd (defender phase), Doji 4th / 5th, Shinjo Special (Q2), attack specializations, extra bonus, Mantis postures / 3rd / 5th, Hiruma 3rd, Ide's banked TN reduction |
| after the roll | 3rd Dan adventure raises, Conviction, Lucky / PCP / Merchant rerolls, Hida 3rd reroll (Q5), Akodo 3rd / 4th, Bayushi 4th, Mirumoto 3rd / 5th, Isawa 3rd TN trade, Courtier 4th temp VP, Priest 3rd pool / 5th ally, Wave Man W1 |
| on damage | flat bonuses (Kakita 4th +5, Courtier +Air, 2nd Dan damage picks, Mantis, Hiruma), Shosuro 5th Dan, Wave Man W4, Conviction on damage, rolled-die sources (Q3) |

**Not applied**, each because an arrow has no such dice pool, TN raise or outcome:

| source | reason |
|---|---|
| double attack's +20 TN and +2 dice on a failed parry; lunge's +1 die | knack mechanics; archery has its own double attack rule |
| Matsu 4th near miss, Otaku 5th trade, Hida 5th bank | Q6 |
| Isawa Duelist Water damage ring, Wave Man W3 weapon floor and W9 recovered dice, Ikoma 4th 10-dice floor, Brotherhood 4th / Mirumoto 4th / Otaku 4th parry modifiers | an arrow has no weapon or ring dice and a failed parry takes no dice away |
| Kitsune Special ring swap | possible, but not in the first build (Later) |

## 8. Out of scope / Later

- [ ] **Defender side.** A "Hit by an arrow" option in the light-wounds modal that adds N serious
  wounds without resetting light wounds, then adds the light wounds and opens the wound check, and
  for an unseen arrow blocks discretionary bonuses on it. Today the defender clicks SW + and LW +.
- [ ] **Evasion as an action-die spend** (+5 TN to arrows for the round, from any phase), shown on the
  combat page's public TN, and the parallel **movement action**.
- [ ] Parry against an arrow costing about 10 ft of movement (no movement tracking exists).
- [ ] Counterattacks against a target that breaks cover or changes direction (uses the existing
  counterattack roll).
- [ ] Kitsune Warden ring swap on arrows.

## 9. Phases

### Phase 0 - Requirements
- [x] Read the rules and survey every attack and damage bonus in the code (section 7)
- [ ] GM answers Q1-Q8; fold them into section 3 and mark them "GM"

### Phase 1 - Pure arithmetic (no answer changes this)
- [ ] `combat_math`: `archery_tn`, `archery_hold_bonus`, `arrow_damage_bands`, `arrow_band_for_d10`, `arrow_damage`
- [ ] Unit tests: the rules' three band examples (excess 12, 22, 50), 45 exactly, a 4 excess (no shift), the band for every d10 face, hold reset (the rules' phase 1 / 2 / 5 example), moving, unseen base 5, every distance band, cover
- [ ] `tests/shared/archery_cases.json` for the TN and hold arithmetic the modal previews, run by pytest and `tests/js/shared_cases.test.js`; the JS twins in `roll_math.js`

### Phase 2 - Formula
- [ ] `build_archery_formula` + `_annotate_attack_type` damage metadata (flat only, plus Q3)
- [ ] The rules' Kakita 4th Dan example as a test: +2k0 +5 attack, +5 damage
- [ ] Tests for a school with every stacked key (Akodo: attack + double attack = +2k0), a flexible pick on iaijutsu, the iaijutsu rank flat, no iaijutsu knack = no flat
- [ ] `archery` in `is_combat_roll`, `_discordant_blocks_void`, `is_wave_man_attack_key`, `_ATTACK_ROLL_KEYS`; 3rd Dan applicability; tests for each
- [ ] Coverage 100%

### Phase 3 - Roll session
- [ ] `build_attack` archery branch (TN parts, hold, extra dice, moving, iaijutsu) with named bonuses; validation refusals tested
- [ ] Extra dice spent and `archery_last_arrow_phase` set on a live roll only; the key in `PER_ROUND_STATE_KEYS` (and so Night's Rest); simulated roll changes nothing
- [ ] `attack.archery` in the answer (TN parts, band odds, raises)
- [ ] `damage` archery branch: d10 band draw, raises, serious wounds, failed parry, cap; `archery:damage` history row
- [ ] Every attack-only action works on an archery session (one test each that it is accepted; the excluded ones refuse)
- [ ] `fight_log` records the serious wounds
- [ ] `tests/test_archery.py`; coverage 100%

### Phase 4 - Sheet
- [ ] Entry points: action-die menu "Archery Attack", Combat Skills "Archery" row with its roll menu
- [ ] Attack modal archery mode: pre-roll inputs (6.4), live TN and hold display, extra-die checkboxes, probability table at the composed TN
- [ ] Hit panel: band table, raises, failed-parry checkbox, serious wounds; damage result panel; unseen note
- [ ] Hide the inapplicable blocks (weapon inputs, Matsu near miss, Otaku trade, Ikoma floor note, W3 / W9)
- [ ] Read-only walk-through leaves the sheet's counters alone; dark mode; phone width; `scripts/build-css.sh`

### Phase 5 - Cards, history, statistics
- [ ] Dice card and history titles; damage card shows band, d10, odds, serious wounds
- [ ] Roll statistics badge and chart on the Archery row; situational notes

### Phase 6 - Clicktests
- [ ] `archery` mark in `pytest.ini`; `tests/e2e/test_archery.py` (forced dice; `save_tracking` before rolling): hit with band draw, hold reset across two arrows, extra dice spent, unseen TN, failed parry, double-attack SW, Kakita stacking visible in the formula, read-only mode, NPC archer from the combat page
- [ ] `COVERAGE.md` entries for every new control and test
- [ ] `test_sheet_js_errors.py` sweep, `test_client_endpoints.py`, a `test_responsive.py` check on the modal at phone width
- [ ] Gate: `pytest tests/e2e/test_archery.py --browser chromium` plus `-k` on the touched attack-modal tests; `node --test tests/js/*.test.js`; the unit suite

### Phase 7 - Land
- [ ] CLAUDE.md: a short "Archery" section and `archery-design/` in the structure list
- [ ] `school-features/*.md`: note archery for the schools whose bonuses now stack onto it
- [ ] Commit, push, deploy (`scripts/deploy.sh`), verify live
