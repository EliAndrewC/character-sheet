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

**Implementation (Phase 4, 5, 9):**
- `app/routes/pages.py`: `school_abilities["mantis_posture_tracking"]` flag gates the tracker block when school is `mantis_wave_treader`.
- `app/templates/character/sheet.html`:
  - `trackingData()` Alpine component gains `posturePhase`, `postureHistory`, `currentPosture()`, `selectPosture(type)`, and `resetMantisRound()`. `setActionDice()` and `clearActionDice()` both call `resetMantisRound()` - those are the two end-of-round triggers per the spec. `selectPosture` / `resetMantisRound` dispatch a `mantis-posture-changed` window event so out-of-scope listeners (the TN display) stay reactive.
  - Attack modal: `atkHitChance` / `atkAvgAttackRoll` read live posture and add +5 to the probability flat. `rollAttack` snapshots the posture at attack-roll time into `formula.flat`, `formula.bonus_sources`, and `formula.bonuses`. `atkComputeDamage` reads live posture and pushes `"+5 flat from offensive posture"` into `parts` + adds 5 to `flat`. Pre-roll Bonuses / Damage bonuses rows overlay the label live.
  - WC modal: `wcProbRow` reads live posture and adds +5 to the probability flat. `rollWoundCheck` snapshots the posture into `formula.flat` and appends `"+5 from defensive posture"` to `formula.bonus_sources`. Pre-roll Bonuses row overlays the label live. (Phase 9 verified that this same flow also carries the 5th Dan defensive-count accumulator and the 3rd Dan defensive accumulator into both the probability table and the post-roll breakdown - see `_mantisLiveWcFlat` / `_mantisLiveWcLabels`.)
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

**Status:** Both branches implemented (Phases 7 + 8).

**Offensive branch (Phase 7):**
- Server flags: `school_abilities["mantis_3rd_dan_offensive"]` (Dan 3+) and `mantis_3rd_dan_x` (= character's attack skill rank).
- The attack-result modal renders a button "Spend another action to increase attack and damage by X for the round" (data-action `mantis-3rd-dan-offensive`, with the rules-text tooltip). Gated on Mantis 3rd Dan + `currentPosture === 'offensive'` + at least one unspent action die; shown on both hit and miss branches.
- Clicking fires `trackingData.incrementMantis3rdDanOffensive(X)`, which spends the lowest unspent action die (labeled `Mantis 3rd Dan (offensive)`) via `spendLowestUnspentActionDie` and adds X to `offensive3rdDanAccum`. Persists via `adventure_state.mantis_offensive_3rd_dan_accum`.
- Feeds the same overlay helpers (`_mantisLiveAttackLabels`, `_mantisLiveAttackFlat`, `atkComputeDamage`) used by Phase 5 and Phase 6, so pre-roll Bonuses + Damage bonuses rows, attack probability, post-roll breakdown, and damage parts all surface the labeled line. `rollAttack` snapshots it into `formula.flat` / `bonus_sources` / `bonuses`.

**Defensive branch (Phase 8):**
- Server flag: `school_abilities["mantis_3rd_dan_defensive"]` (Dan 3+). Reuses `mantis_3rd_dan_x` for X.
- The Tracking-section posture-tracker block renders a button "Spend action to increase TN and wound checks by X" (data-action `mantis-3rd-dan-defensive`, with the rules-text tooltip). Gated on Mantis 3rd Dan + `currentPosture === 'defensive'` + at least one unspent action die.
- Clicking fires `trackingData.incrementMantis3rdDanDefensive(X)`, which spends the lowest unspent action die (labeled `Mantis 3rd Dan (defensive)`) and adds X to `defensive3rdDanAccum`. Persists via `adventure_state.mantis_defensive_3rd_dan_accum`.
- Feeds `_mantisLiveWcLabels` / `_mantisLiveWcFlat` and `rollWoundCheck`, so the WC modal's pre-roll Bonuses + post-roll breakdown + probability table include the labeled +X (stacks additively with Phase 5 current-posture +5 and Phase 6 5th Dan defensive accumulator).
- TN display: local x-data now carries a `defensive3rdDan` field and a `has3rdDan` flag; `total()` adds it to the displayed value, `tooltip()` enumerates it, and a `tn-3rd-dan-accumulator` inline label renders `+X 3rd Dan` alongside the existing `tn-defensive-bump` (+5 defensive posture) and `tn-5th-dan-accumulator` (+N 5th Dan) labels.

**Clear bonuses + end-of-round wiring (Phase 8):**
- The posture-tracker block renders a "Clear bonuses" button (data-action `mantis-clear-bonuses`) visible whenever any per-round state is non-zero (`actionDice.length > 0 || postureHistory.length > 0 || offensive3rdDanAccum > 0 || defensive3rdDanAccum > 0`). Clicking delegates to `clearActionDice()`, which wipes actionDice and calls `resetMantisRound()`.
- `resetMantisRound()` now zeros `defensive3rdDanAccum` alongside `offensive3rdDanAccum`, postureHistory, and posturePhase - so rolling initiative, clicking the action-dice "Clear" button, OR clicking "Clear bonuses" all have the same effect (end-of-round reset).
- The `mantis-posture-changed` event detail now also carries `offensive3rdDan` and `defensive3rdDan` so the TN display (and any future cross-scope listener) can react to 3rd Dan accumulator changes without a separate event.

**Unit tests:** `tests/test_routes.py::TestMantisPostureTracking` - all prior Phase 7 tests plus `test_mantis_3rd_dan_defensive_flag_at_dan_3`, `test_mantis_2nd_dan_does_not_have_3rd_dan_defensive`, `test_non_mantis_does_not_have_3rd_dan_defensive`, `test_mantis_3rd_dan_defensive_button_markup_present`, `test_mantis_2nd_dan_no_3rd_dan_defensive_button`, `test_mantis_3rd_dan_defensive_accum_state_roundtrips`, `test_mantis_3rd_dan_defensive_accum_hydrates`, `test_tn_display_has_3rd_dan_accumulator_wiring`, `test_tn_display_dan_2_mantis_has3rdDan_false`.

**Clicktests:** `tests/e2e/test_school_abilities.py` - all prior Phase 7 tests plus `test_mantis_3rd_dan_defensive_button_hidden_without_posture`, `test_mantis_3rd_dan_defensive_button_hidden_in_offensive_posture`, `test_mantis_3rd_dan_defensive_button_hidden_no_action_dice`, `test_mantis_3rd_dan_defensive_button_absent_on_dan_2`, `test_mantis_3rd_dan_defensive_click_spends_die_and_accumulates`, `test_mantis_3rd_dan_defensive_two_spends_stack`, `test_mantis_3rd_dan_defensive_wc_overlay`, `test_mantis_3rd_dan_defensive_tn_display`, `test_mantis_clear_bonuses_zeros_everything`, `test_mantis_clear_bonuses_button_hidden_when_empty`, `test_mantis_action_dice_clear_equivalent_to_clear_bonuses`.

---

## 4th Dan

> Raise the current and maximum rank of your School Ring by 1. Raising that Ring now costs 5 fewer XP. Begin each combat round with an athletics action die set to 1, which may only be spent on movement, athletics actions, or your 3rd Dan technique.

**Status:** Implemented (Phase 10).

- **Ring raise:** Works out of the box. `calculate_ring_xp()` and the editor's `enforceFourthDanRing()`, `schoolRingMin()`, `ringMax()`, `getSchoolRing()` all read `school_ring_choice`, so whichever ring the Mantis picked from the "Any" option at creation (per Phase 1 - Void by default) gets the 4th Dan free +1, the ceiling bump to 7, and the 5-XP-per-raise discount above 4. No code changes were needed for the ring raise itself.
- **Bonus athletics action die:** `build_initiative_formula()` exposes a new boolean flag `mantis_4th_dan_athletics_die` (true when Mantis + Dan >= 4). The initiative-roll post-processing on the client pushes `{value: 1, athletics_only: true, mantis_4th_dan: true}` into the dice array after all other school effects fire. `setActionDice` preserves both `athletics_only` and `mantis_4th_dan` flags through the tracker round-trip. The action-die rendering picks up a `data-die-mantis-4th-dan` attribute and a dedicated tooltip ("Mantis 4th Dan athletics die. May only be spent on movement, athletics, or the Mantis 3rd Dan technique."). Reuses the existing `athletics_only` CSS class (blue variant) for visual distinction and the existing auto-spend skip so non-athletics auto-spends won't pick this die. Regenerated on every initiative roll; cleared by Clear bonuses or the action-dice Clear button.

**Unit tests:**
- `tests/test_xp.py::TestMantisFourthDanRingRaise` - parametrized across all five ring choices (Air/Fire/Earth/Water/Void): auto-raise to 4 is free, 5-XP discount per raise above 4, no discount at Dan 3, and non-school rings are unaffected.
- `tests/test_dice.py::TestMantisWaveTreader4thDanAthleticsDie` - flag true at Dan 4/5, false at Dan 3/1, false for non-Mantis, and the formula's rolled/kept counts are unchanged (bonus die is appended post-roll, not part of the rolled set).

**Clicktests:** `tests/e2e/test_school_abilities.py` - `test_mantis_4th_dan_athletics_die_appended_after_initiative`, `test_mantis_4th_dan_die_renders_with_testable_markup`, `test_mantis_4th_dan_die_spendable`, `test_mantis_4th_dan_die_regenerated_on_next_initiative`, `test_mantis_4th_dan_die_cleared_by_clear_bonuses`, `test_mantis_dan_3_no_4th_dan_die`, `test_non_mantis_dan_4_no_4th_dan_die`.

---

## 5th Dan

> For each phase in which you declare an offensive posture, you gain +1 to all attack and damage rolls for the remainder of the round. For each phase in which you choose a defensive posture, you gain +1 to your wound checks and your TN to be hit for the remainder of the round.

**Status:** Implemented (Phase 6). Built on top of the posture tracker:
- `offensivePhaseCount()` and `defensivePhaseCount()` are derived from `postureHistory` (no separate state), so they auto-reset whenever `resetMantisRound()` fires (initiative roll or action-dice Clear) along with the rest of Phase 4's round-tracker state.
- The "Accumulated 5th Dan bonuses" sub-block appears under the posture tracker (testid `mantis-5th-dan-accumulator`) on Dan 5 Mantis sheets whenever either count > 0. Lines: "+N to attack and damage rolls" when offensive > 0; "+M to wound checks and TN" when defensive > 0.
- Attack/damage integration reuses the same overlay helpers (`_mantisLiveAttackLabels`, `_mantisLiveAttackFlat`, `_mantisLiveDamageLabels`, `_mantisLiveWcLabels`, `_mantisLiveWcFlat`). These combine the Phase 5 current-posture +5 with the 5th Dan accumulator; the labeled entries go into pre-roll rows, probability tables, and post-roll breakdowns. `rollAttack` and `rollWoundCheck` snapshot the accumulator into `formula.flat` / `formula.bonus_sources` / `formula.bonuses` at roll time, and `atkComputeDamage` adds the labeled line to `parts` with the flat added so both pre-roll preview and post-roll damage-result breakdown show it.
- TN display: local x-data tracks `defensiveCount` (populated from the enriched `mantis-posture-changed` event detail) in addition to `posture`. The displayed TN is `base + (posture==='defensive' ? 5 : 0) + (accum ? defensiveCount : 0)`. The tooltip enumerates each contributing bonus. A `tn-5th-dan-accumulator` label (`+N 5th Dan`) renders alongside the existing `tn-defensive-bump` label when the accumulator applies.

**Server flag:** `school_abilities["mantis_posture_accumulation"]` in `app/routes/pages.py` is `True` when school is Mantis Wave-Treader AND Dan >= 5. Gates the `<div>` sub-block and feeds the `accum` flag in the TN display's x-data scope.

**Unit tests:** `tests/test_routes.py::TestMantisPostureTracking` — `test_mantis_5th_dan_has_posture_accumulation_flag`, `test_mantis_4th_dan_does_not_have_posture_accumulation_flag`, `test_non_mantis_does_not_have_posture_accumulation_flag`, `test_mantis_5th_dan_accumulator_block_renders`, `test_mantis_4th_dan_accumulator_block_absent`, `test_tn_display_5th_dan_accumulator_wiring_present`, `test_tn_display_dan_4_mantis_accum_false`.

**Clicktests:** `tests/e2e/test_school_abilities.py` — `test_mantis_5th_dan_accumulator_block_hidden_with_no_history`, `test_mantis_5th_dan_accumulator_block_absent_at_dan_4`, `test_mantis_5th_dan_accumulator_counts_offensive`, `test_mantis_5th_dan_accumulator_counts_mixed`, `test_mantis_5th_dan_accumulator_resets_on_initiative`, `test_mantis_5th_dan_attack_modal_pre_roll_includes_accumulator`, `test_mantis_5th_dan_attack_post_roll_snapshot`, `test_mantis_5th_dan_damage_accumulator_in_parts`, `test_mantis_5th_dan_wc_modal_defensive_accumulator`, `test_mantis_5th_dan_tn_display_bumps_with_accumulator`, `test_mantis_dan_4_no_accumulator_on_attack`.

---

## Test References

Each section above lists its concrete unit + clicktest references inline. A bird's-eye summary:

- **Unit tests:**
  - `tests/test_game_data.py` - school registration, `SCHOOL_RING_OPTIONS["mantis_wave_treader"]`, bushi categorization, school knack validation (Phase 1).
  - `tests/test_dice.py::TestMantisWaveTreader1stDan` - 1st Dan extra die on initiative / athletics / wound check (Phase 2).
  - `tests/test_dice.py::TestMantisWaveTreader2ndDan`, `TestMantis2ndDanEligibleChoices` - 2nd Dan flexible free raise (Phase 3).
  - `tests/test_dice.py::TestMantisWaveTreader4thDanAthleticsDie` - 4th Dan deterministic bonus-die flag in `build_initiative_formula` (Phase 10).
  - `tests/test_xp.py::TestMantisFourthDanRingRaise` - 4th Dan ring-raise discount + auto-raise across all five ring choices (Phase 10).
  - `tests/test_routes.py::TestMantisPostureTracking` - server-side flag gating and markup wiring for `mantis_posture_tracking`, `mantis_posture_accumulation`, `mantis_3rd_dan_offensive`, `mantis_3rd_dan_defensive`, plus adventure_state roundtrips (Phases 4-8).
  - `tests/test_editor_controls.py` - editor-side Mantis defaults (Void auto-raise, school-ring Any picker) (Phase 1).

- **Clicktests:** everything under `@pytest.mark.school_abilities` in `tests/e2e/test_school_abilities.py` named `test_mantis_*` covers Phases 1-10 end-to-end. The companion `tests/e2e/COVERAGE.md` has one checkbox per interactive behaviour with the test-function reference.

- **Pytest marks:** the Mantis suite is consolidated under the `school_abilities` mark. Run `pytest tests/e2e/ -m school_abilities --browser chromium` to exercise just the Mantis clicktests (~4 minutes at the time of Phase 10 completion).
