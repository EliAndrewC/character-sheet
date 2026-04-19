# Mantis Wave-Treader

**School ID:** `mantis_wave_treader`
**Category:** Bushi
**School Ring:** "Any" - Player chooses from Air, Fire, Earth, Water, or Void. Requires a new value in the `school_ring` → `SCHOOL_RING_OPTIONS` mapping ("Any" expands to all five rings, unlike "any non-Void" which excludes Void). Default ring is Void - Mantis Wave-Treader is the only school with a Void default; every other variable-ring school continues to default to Water.
**School Knacks:** athletics, iaijutsu, worldliness - Athletics is rollable (varies by ring used; opens the four-ring picker with void submenus - same as Togashi). Iaijutsu is rollable (Air during stance phase; see `dice.py`). Worldliness is the existing non-rollable knack (passive, `ring=None`) already used by Priest.

---

## Special Ability

> Each phase you select an "offensive" or "defensive" posture. While fighting with an offensive posture, you get a free raise to all attack and damage rolls, and while fighting in a defensive posture you get a free raise to wound checks and your TN to be hit is increased by 5.

**Status:** Implemented (Phases 4 + 5). The per-phase posture tracker renders in the Tracking section with two buttons - "Offensive Posture for Phase X" and "Defensive Posture for Phase X" - that advance X from 1 through 10 and then disable. Rolling initiative or clicking the action-dice "Clear" button resets X back to 1 and empties the posture history. Selections persist across page reloads via `adventure_state`. The current posture drives live mechanical overlays:
- **Offensive:** +5 flat to attack rolls (labeled in pre-roll Bonuses row, post-roll breakdown, and `formula.bonuses`) and +5 flat to damage rolls (labeled in pre-roll Damage bonuses row and post-roll damage-result breakdown via `atkComputeDamage` / `atkDamageParts`).
- **Defensive:** +5 flat to wound checks (labeled in WC modal pre-roll Bonuses row and post-roll breakdown via `formula.bonus_sources`) and +5 to the sheet's TN-to-be-hit display (with a tooltip explaining the bump).
- The posture tracker itself shows an "Active bonuses:" summary line beneath the current-posture line.

**Implementation (Phase 4 + 5):**
- `app/routes/pages.py`: `school_abilities["mantis_posture_tracking"]` flag gates the tracker block when school is `mantis_wave_treader`.
- `app/templates/character/sheet.html`:
  - `trackingData()` Alpine component gains `posturePhase`, `postureHistory`, `currentPosture()`, `selectPosture(type)`, and `resetMantisRound()`. `setActionDice()` and `clearActionDice()` both call `resetMantisRound()` - those are the two end-of-round triggers per the spec. `selectPosture` / `resetMantisRound` dispatch a `mantis-posture-changed` window event so out-of-scope listeners (the TN display) stay reactive.
  - Attack modal: `atkHitChance` / `atkAvgAttackRoll` read live posture and add +5 to the probability flat. `rollAttack` snapshots the posture at attack-roll time into `formula.flat`, `formula.bonus_sources`, and `formula.bonuses`. `atkComputeDamage` reads live posture and pushes `"+5 flat from offensive posture"` into `parts` + adds 5 to `flat`. Pre-roll Bonuses / Damage bonuses rows overlay the label live.
  - WC modal: `wcProbRow` reads live posture and adds +5 to the probability flat. `rollWoundCheck` snapshots the posture into `formula.flat` and appends `"+5 from defensive posture"` to `formula.bonus_sources`. Pre-roll Bonuses row overlays the label live.
  - TN display (top derived stats): now has its own `x-data` with a `mantis-posture-changed.window` listener; bumps the displayed value by 5 and shows a "+5 defensive posture" label with a tooltip when defensive.
- Storage: `adventure_state.mantis_posture_phase` and `adventure_state.mantis_posture_history`. No schema change.

**Unit tests:** `tests/test_routes.py::TestMantisPostureTracking` (flag present on Mantis / absent on non-Mantis, tracker markup renders / does not render, state roundtrips through `POST /track`, state rehydrates from `adventure_state` on reload, posture bonus summary block is present, TN display has the Alpine overlay wiring).

**Clicktests:** `tests/e2e/test_school_abilities.py` -
- Phase 4 (tracker UI): `test_mantis_posture_tracker_visibility`, `test_mantis_posture_tracker_absent_on_non_mantis`, `test_mantis_posture_tracker_advance`, `test_mantis_posture_tracker_disable_at_11`, `test_mantis_posture_tracker_reset_on_initiative`, `test_mantis_posture_tracker_reset_on_action_dice_clear`.
- Phase 5 (posture bonuses): `test_mantis_posture_tracker_bonus_summary_offensive`, `test_mantis_posture_tracker_bonus_summary_defensive`, `test_mantis_posture_tracker_bonus_summary_toggles`, `test_mantis_offensive_posture_attack_pre_roll_bonuses`, `test_mantis_offensive_posture_attack_post_roll_breakdown`, `test_mantis_offensive_posture_damage_preview_and_result`, `test_mantis_defensive_posture_tn_display_bumps`, `test_mantis_defensive_posture_wc_modal_overlay`, `test_mantis_no_posture_no_overlay`.

---

## 1st Dan

> Roll one extra die on initiative, athletics, and wound checks.

**Status:** Implemented (Phase 2). Data-only via the existing `SCHOOL_TECHNIQUE_BONUSES` mechanism.
- `app/game_data.py`: `SCHOOL_TECHNIQUE_BONUSES["mantis_wave_treader"]["first_dan_extra_die"] = ["initiative", "athletics", "wound_check"]`.
- Applied by `app/services/dice.py:_apply_school_technique_bonus()` for athletics, `build_wound_check_formula()` for wound checks, and `build_initiative_formula()` for initiative. No new code was required beyond the `game_data.py` entry.

**Unit tests:** `tests/test_dice.py::TestMantisWaveTreader1stDan` (initiative / athletics / wound-check extra die at Dan 1+, no bonus at Dan 0, no bleed onto attack).
**Clicktests:** `tests/e2e/test_school_abilities.py::test_mantis_1st_dan_formula_extra_die` (verifies the sheet-embedded roll formulas include the extra die for initiative, athletics across all four rollable rings, and wound check, plus a labeled `1st Dan` entry in `wound_check.bonus_sources`).

---

## 2nd Dan

> You get a free raise on a type of roll of your choice.

**Status:** Implemented (Phase 3). Player picks one roll type; +5 flat bonus applies to matching rolls at Dan >= 2.

- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` (flexible - player picks at Dan 2 advancement).
- The chosen value is stored in the `technique_choices` JSON column under the `mantis_2nd_dan_free_raise` key.
- Applied as a +5 flat bonus:
  - `app/services/dice.py:_apply_school_technique_bonus()` covers skills, rollable knacks, attack, and parry.
  - `app/services/dice.py:build_wound_check_formula()` covers the wound-check choice (labeled in `bonus_sources`).
  - `app/services/dice.py:_annotate_attack_type()` covers the damage choice (adds to `damage_flat_bonus` and `damage_bonus_sources`).
- Editor UI: `app/templates/character/edit.html` renders a `data-testid="mantis-2nd-dan-picker"` dropdown when `school == 'mantis_wave_treader' && currentDan() >= 2`. Options: all rollable skills, the school's rollable knacks (via `mantisEligibleKnacks()`), and the combat rolls (attack, damage, parry, wound_check). Initiative and non-rollable knacks are excluded.
- Server-side validation: `app/routes/characters.py` autosave rejects any value not in `mantis_2nd_dan_eligible_choices(school_id)` (in `app/services/dice.py`), so a crafted POST can't persist `initiative` or `worldliness`.
- **Sheet display:**
  - The attack modal's pre-roll panel gets a new "Damage bonuses:" row fed by `damage_bonus_sources` (`app/templates/character/sheet.html`).
  - `atkComputeDamage()` pushes an explicit `"+5 flat from 2nd Dan"` line into `atkDamageParts` when the damage source is present, so the post-roll damage breakdown shows the label.

**Unit tests:** `tests/test_dice.py::TestMantisWaveTreader2ndDan` (+5 per eligible choice, none when not chosen, no bonus below Dan 2, damage-side via `_annotate_attack_type`, no bleed to non-Mantis schools). `tests/test_dice.py::TestMantis2ndDanEligibleChoices` (helper returns the right set). `tests/test_routes.py` covers the autosave validation (rejects initiative / worldliness, accepts valid picks, allows clearing).

**Clicktests:** `tests/e2e/test_school_abilities.py::test_mantis_2nd_dan_editor_picker_visible_and_saves`, `test_mantis_2nd_dan_attack_choice_labeled`, `test_mantis_2nd_dan_parry_choice_labeled`, `test_mantis_2nd_dan_skill_choice_labeled`, `test_mantis_2nd_dan_knack_choice_labeled`, `test_mantis_2nd_dan_wound_check_choice_labeled`, `test_mantis_2nd_dan_damage_choice_labeled`, `test_mantis_2nd_dan_switch_choice_moves_bonus`.

---

## 3rd Dan

> After making an attack roll during a phase in which you have chosen an offensive posture, you may spend one action die from any phase to give yourself +X to all attack and damage rolls for the rest of the round, where X is your attack skill.
>
> After seeing the result of an attack roll made against you while fighting with a defensive posture, you may spend one action die from any phase to increase your wound checks and TN to be hit by X for the remainder of the round, where X is your attack skill.

**Status:** Not yet implemented. Non-standard 3rd Dan (no `third_dan` config block - too bespoke). Requires:
- **Offensive branch** - The attack-roll result modal shows a button "Spend another action to increase attack and damage by X for the round" (X = attack skill) when the character is Mantis Wave-Treader at Dan >= 3, the current phase's posture is offensive, and at least one action die is still unspent. Tooltip carries the rules text verbatim. Clicking marks the lowest unspent action die spent and adds X to an `offensive3rdDan` accumulator that applies to all subsequent attack rolls and damage rolls until the next initiative roll.
- **Defensive branch** - A button "Spend action to increase TN and wound checks by X" (X = attack skill) shown in the Tracking section below the posture-bonus list while in a defensive posture, with rules-text tooltip. Clicking spends one action die and adds X to a `defensive3rdDan` accumulator that applies to all wound checks and to the displayed TN until the next initiative roll.
- Both accumulators reset on initiative roll, and both are zeroed by the "Clear bonuses" button and by the action-dice "Clear" button.
- The wound check modal's probability table displays these accumulators as additive bonuses and factors them into the "% chance" and "average serious wounds" computations.

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## 4th Dan

> Raise the current and maximum rank of your School Ring by 1. Raising that Ring now costs 5 fewer XP. Begin each combat round with an athletics action die set to 1, which may only be spent on movement, athletics actions, or your 3rd Dan technique.

**Status:** Not yet implemented.
- **Ring raise** - The Dan 4 raise applies to the player's chosen school ring (picked from the "Any" option at character creation - per Phase 1, Mantis defaults to Void). The player may not redirect this raise to a different ring. This is the standard behaviour enforced by `enforceFourthDanRing()` / `calculate_ring_xp()`, so it should work for Mantis once those functions read `school_ring_choice` rather than the static `school_ring` value.
- **Bonus athletics action die** - After rolling initiative, render a blue "1" die (always value 1, never rolled) alongside the standard action dice. This is analogous to the Togashi Ise Zumi's "1 athletics action" die, but it is always a literal 1 and is always present regardless of which initiative variant the player picks. The die is restricted in spending to movement, athletics rolls, or the Mantis 3rd Dan technique (offensive or defensive branch). The app tracks the restriction as a label/tooltip; action-die spending enforcement is lightweight (display-only, same approach as Togashi's athletics-only dice today).

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## 5th Dan

> For each phase in which you declare an offensive posture, you gain +1 to all attack and damage rolls for the remainder of the round. For each phase in which you choose a defensive posture, you gain +1 to your wound checks and your TN to be hit for the remainder of the round.

**Status:** Not yet implemented. Built on top of the posture tracker:
- Track two running counters per round: `offensivePhaseCount`, `defensivePhaseCount`. Incremented each time the player clicks the respective posture button.
- Display "Accumulated 5th Dan bonuses" under the posture list:
  - +`offensivePhaseCount` to attack and damage rolls (all subsequent rolls this round).
  - +`defensivePhaseCount` to wound checks and TN to be hit.
- Both counters reset to 0 on initiative roll. They are NOT cleared by the posture "Clear bonuses" button (since those bonuses are already "spent into" the round and the player wouldn't want to retroactively unwind them) - but see implementation plan for the open question.
- Accumulators integrate into the same pathways as the 3rd Dan accumulators (attack/damage bonuses on attack roll modal; wound-check bonuses and TN display on the sheet; wound check probability table).

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## Test References

To be populated as the phases land.
