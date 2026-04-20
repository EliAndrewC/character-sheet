# Kakita Duelist

**School ID:** `kakita_duelist`
**Category:** Duelist
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> Your 10s on initiative rolls are considered to be in a special Phase 0. You may use interrupt actions to attack using iaijutsu, and any Phase 0 attacks use iaijutsu.

**Status:** Fully implemented (Phases 1-5). Kakita correctly keeps 10s as Phase 0 on initiative, renders them distinctly, restricts their per-die menu to a single Iaijutsu Attack option that opens the attack modal, applies the 3rd Dan defender-phase bonus on every attack with live probability-chart updates, exposes a Phase-0 Interrupt button that spends the 2 highest dice as a cost to launch an iaijutsu attack at attacker phase 0, and provides a dedicated once-per-round 5th Dan contested-iaijutsu modal with ±1-die damage scaling per 5-point gap.

**Phase-0 Interrupt implementation:**
- Tracking-side (`window._trackingBridge`): new `kakitaPhase0Interrupt()` spends the two highest-valued unspent non-athletics-only action dice (Phase-0 dice with value 0 are the LAST picks under the "highest" sort, matching the rules' "2 highest dice" cost), labels them `"Kakita Phase 0 interrupt"`, persists via `save()`, then calls `window._diceRoller.openKakitaPhase0InterruptModal()`.
- Dice-roller-side: `openKakitaPhase0InterruptModal()` opens the `knack:iaijutsu:attack` attack modal and sets `atkForceAttackerPhase = 0` + `atkKakitaInterrupt = true`.
- Attack modal: the interrupt banner "Phase 0 Kakita interrupt attack (2 highest dice spent)" replaces the generic Phase-0-die banner. The Kakita 3rd Dan control keeps showing and uses the forced attacker phase of 0. The initiative warning is suppressed when `atkForceAttackerPhase` is set (the cost was paid deliberately).
- `rollAttack()` skips `_autoSpendActionDie` when `atkForceAttackerPhase` is set, so the interrupt does not consume a third die. Closing the modal without rolling leaves the 2 dice spent (no refund).

**Implementation:**
- `build_initiative_formula` in `app/services/dice.py` sets `kakita_phase_zero=True` on the initiative formula for `kakita_duelist`.
- `app/routes/pages.py` exposes `school_abilities.kakita_phase_zero=True` so the rest of the client can gate Kakita-only UI without reading the initiative formula cross-scope.
- `runRoll()` in `app/templates/character/sheet.html` uses a `sortValue(v)` helper that maps `10 -> 0` when the initiative formula carries `kakita_phase_zero`. The keep-lowest slice then picks up any rolled 10 first, and the existing `v === 10 ? 0 : v` rewrite converts kept 10s to value-0 action dice. Non-10 dice are untouched.
- The Actions-panel SVG already paints `.phase-zero` on any value-0 die (from `base.html` CSS); the per-die tooltip reads "Phase 0 (Kakita interrupt): iaijutsu attacks only." when `school_abilities.kakita_phase_zero` is set.
- Persistence: the 0-valued dice flow into `window._trackingBridge.setActionDice` → `save()` → `_sanitize_action_dice` (which preserves `value`), so the 0s survive a page reload.
- **Phase-0 dice are restricted to iaijutsu attacks (Phase 2).** The per-die menu splits into two branches on `kakita_phase_zero`: value-0 dice get a single "Iaijutsu Attack" item plus "Mark as spent"; value > 0 dice see the unchanged full menu. Clicking Iaijutsu Attack routes through `rollForActionDie('knack:iaijutsu:attack', i)` and opens the attack modal with `attack_variant='iaijutsu'`. The attack modal's pre-roll page shows a "Kakita Phase 0 iaijutsu attack" gold banner for any iaijutsu-variant attack.
- **`knack:iaijutsu:attack` formula.** `build_all_roll_formulas` in `dice.py` exposes this as a Kakita-only sibling of `knack:iaijutsu`, flagged `is_attack_type=True` and carrying the iaijutsu damage metadata (including the +5 from 4th Dan when applicable). Non-Kakita characters with iaijutsu knack do not get this key.

**Design note:** `build_initiative_formula` already sets `reroll_tens=False` for every school, so a kept 10 truly reads as 10 on the client. No Kakita-specific reroll override was needed.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_kakita_phase_zero_flag`
- `test_dice.py::TestSchoolAbilities::test_non_kakita_initiative_no_phase_zero_flag`
- `test_routes.py::TestKakitaPhaseZeroFlag::test_kakita_has_phase_zero_flag`
- `test_routes.py::TestKakitaPhaseZeroFlag::test_non_kakita_does_not_have_phase_zero_flag`
- `test_dice.py::TestSchoolAbilities::test_kakita_iaijutsu_attack_formula_exposed`
- `test_dice.py::TestSchoolAbilities::test_non_kakita_no_iaijutsu_attack_formula`
- `test_dice.py::TestSchoolAbilities::test_kakita_iaijutsu_attack_formula_mirrors_iaijutsu_knack_rolled_kept`
- `test_dice.py::TestSchoolAbilities::test_kakita_iaijutsu_attack_formula_respects_4th_dan_damage_bonus`
- `test_dice.py::TestSchoolAbilities::test_kakita_below_4th_dan_iaijutsu_attack_no_damage_bonus`

**Clicktests:**
- `test_school_abilities.py::test_kakita_phase_0_behavioral`
- `test_school_abilities.py::test_kakita_initiative_keeps_10_over_higher_lower_dice`
- `test_school_abilities.py::test_kakita_initiative_two_10s_both_become_phase_0`
- `test_school_abilities.py::test_non_kakita_10_on_initiative_is_unkept`
- `test_school_abilities.py::test_kakita_phase_0_die_has_phase_zero_svg_class`
- `test_school_abilities.py::test_kakita_phase_0_die_survives_reload`
- `test_school_abilities.py::test_kakita_phase_0_die_tooltip_mentions_iaijutsu`
- `test_school_abilities.py::test_kakita_phase_zero_die_menu_shows_only_iaijutsu_attack`
- `test_school_abilities.py::test_kakita_non_zero_die_menu_unchanged`
- `test_school_abilities.py::test_kakita_phase_zero_menu_opens_attack_modal_for_iaijutsu`
- `test_school_abilities.py::test_kakita_phase_zero_attack_modal_notes_interrupt`
- `test_school_abilities.py::test_kakita_phase_zero_attack_spends_the_clicked_die`
- `test_school_abilities.py::test_non_kakita_with_iaijutsu_does_not_expose_iaijutsu_attack_key`
- `test_sheet_js_errors.py` includes `kakita_duelist` in the school list.
- `test_school_selection.py` references `kakita_duelist` for selection testing.

---

## 1st Dan

> Roll one extra die on double attack, iaijutsu, and initiative rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "iaijutsu", "initiative"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_initiative_formula()`.

**Unit tests:** None specific to Kakita 1st Dan.
**Clicktests:**
- `test_school_abilities.py::test_kakita_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on all iaijutsu rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "iaijutsu"`
- Applied as +5 flat bonus on iaijutsu rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_kakita_2nd_dan_iaijutsu_bonus`

---

## 3rd Dan

> Your attacks get a bonus of X for each phase before the defender's next action they occur, where X is equal to your attack skill. If a defender does not have an action remaining in this round, they are considered to act in phase 11. This applies to all types of attacks, and you know the next action of everyone within striking range.

**Status:** Fully implemented on the attack modal. The "you know the next action of everyone within striking range" information-display piece is player-knowledge and not modeled in the app.

**Implementation:**
- Server: `app/services/dice.py` stamps `kakita_3rd_dan_defender_phase_bonus = True` on every attack-type formula (base attack, attack-variant knacks, athletics-attack, and the Phase-2 `knack:iaijutsu:attack`) for Kakita 3rd Dan+. `app/routes/pages.py` exposes `school_abilities.kakita_3rd_dan_defender_phase_bonus_x = attack_skill` (0 when not 3rd Dan+).
- Client: the attack modal's pre-roll page renders a dropdown for the defender's next action (1-10 and an 11-labeled "no remaining actions" default, per the rules). The control is gated on the formula flag, a non-zero X, the initiative warning not firing, and an action die being available. The bonus is `max(0, defender_phase - attacker_phase) * X`, where attacker_phase = the to-be-spent die's value (Phase-0 dice count as 0). `atkHitChance` and `atkAvgAttackRoll` consume the bonus so the probability chart updates live. `rollAttack()` snapshots `kakita_3rd_dan_bonus / _attacker_phase / _defender_phase / _x` onto the formula for the post-roll breakdown.

**Questions (ANSWERED):**
- The bonus is X per phase before the defender's next action, where X is the attack skill rank.
- Phase tracking is needed: if defender's next action is phase 7 and you attack in phase 4, bonus = 3X.
- "Defender is considered to act in phase 11" if they have no remaining actions.
- "You know the next action of everyone within striking range" is an information display mechanic.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_kakita_3rd_dan_attack_flag_set`
- `test_dice.py::TestSchoolAbilities::test_kakita_3rd_dan_parry_no_flag`
- `test_dice.py::TestSchoolAbilities::test_kakita_3rd_dan_attack_knack_flags`
- `test_dice.py::TestSchoolAbilities::test_kakita_3rd_dan_athletics_attack_flag`
- `test_dice.py::TestSchoolAbilities::test_kakita_3rd_dan_iaijutsu_attack_flag`
- `test_dice.py::TestSchoolAbilities::test_kakita_below_3rd_dan_no_defender_phase_flag`
- `test_dice.py::TestSchoolAbilities::test_kakita_3rd_dan_flag_only_for_kakita_school`

**Clicktests:**
- `test_school_abilities.py::test_kakita_3rd_dan_defender_phase_control_hidden_without_initiative`
- `test_school_abilities.py::test_kakita_3rd_dan_defender_phase_control_hidden_out_of_dice`
- `test_school_abilities.py::test_kakita_3rd_dan_defender_phase_control_visible_with_action_dice`
- `test_school_abilities.py::test_kakita_3rd_dan_bonus_applied_to_attack_roll`
- `test_school_abilities.py::test_kakita_3rd_dan_bonus_clamps_when_defender_acts_first`
- `test_school_abilities.py::test_kakita_3rd_dan_bonus_shifts_probability_chart`
- `test_school_abilities.py::test_kakita_3rd_dan_bonus_uses_clicked_die_value`
- `test_school_abilities.py::test_kakita_3rd_dan_phase_11_default_is_no_remaining_actions`
- `test_school_abilities.py::test_kakita_below_3rd_dan_no_bonus_control`
- `test_school_abilities.py::test_kakita_3rd_dan_bonus_on_phase_zero_die`

---

## 4th Dan

> Raise your current and maximum Fire by 1. Raising your Fire now costs 5 fewer XP. You get a free raise to all damage rolls from attacks using iaijutsu.

**Status:** Fully implemented.
- Ring raise (+1 Fire, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Free raise on iaijutsu DAMAGE rolls" is fully implemented via `app/services/dice.py:build_all_roll_formulas()` (iaijutsu damage metadata with +5 flat bonus when school_id == "kakita_duelist" and dan >= 4).

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_kakita_duelist_4th_dan_iaijutsu_damage_bonus` - verifies +5 flat on iaijutsu damage at 4th Dan
- `test_dice.py::TestSchoolAbilities::test_kakita_duelist_below_4th_dan_no_damage_bonus` - verifies no bonus below 4th Dan
**Clicktests:**
- `test_school_abilities.py::test_kakita_4th_dan_iaijutsu_damage_bonus`

---

## 5th Dan

> At the beginning of phase 0 in each combat round, make a contested iaijutsu roll against an opponent. If the opponent doesn't have iaijutsu, they may roll attack instead, and you get an extra free raise. Make a damage roll against this opponent; if you won the contested roll then roll 1 extra damage die for every 5 by which your roll exceeded your opponent's, and if you lost then roll 1 fewer damage die for every 5 by which their roll exceeded yours.

**Status:** Fully implemented via a dedicated modal.

**Implementation:**
- Server: `app/routes/pages.py` exposes `school_abilities.kakita_5th_dan_phase_zero_contest = True` (Kakita Duelist at Dan ≥ 5 only).
- Tracking bridge: new `kakita5thDanUsed` flag (persisted via `adventureState.kakita_5th_dan_used`); cleared by `setActionDice()` on the next initiative roll so the ability refreshes each round.
- Dice roller: dedicated `k5Open/k5Phase` modal state with 'pre' / 'result' / 'damage-result' phases plus `k5OpponentHasIaijutsu`, `k5DefenderPhase`, `k5WeaponRolled/Kept`, and scratch state for the roll/damage results. `openKakita5thDanModal()` resets + opens; `rollKakita5thDanContest()` rolls iaijutsu with +5 no-iaijutsu bonus and the 3rd-Dan-at-attacker-phase-0 bonus (reusing the same X = attack skill plumbing as Phase 3); `rollKakita5thDanDamage()` computes `diff = player - opponent`, adjusts rolled dice by `floor(diff/5)` (positive = extra, negative = fewer), clamps to L7R 10k10 caps, rolls damage, and then flips `kakita5thDanUsed`.
- UI: a Kakita-only "Kakita 5th Dan" panel in the tracking area with a "Phase 0 Contested Iaijutsu" button (disabled when `kakita5thDanUsed`) plus a dedicated `data-modal="kakita-5th-dan"` modal that walks the player through checkbox + defender-phase picker → roll → opponent-roll input → damage roll → damage total.
- Cancelling via the × before rolling does NOT consume the once-per-round flag (checked post-damage-roll only).

**Unit tests:**
- `test_routes.py::TestKakitaPhaseZeroFlag::test_kakita_5th_dan_has_phase_zero_contest_flag`
- `test_routes.py::TestKakitaPhaseZeroFlag::test_kakita_below_5th_dan_no_phase_zero_contest_flag`
- `test_routes.py::TestKakitaPhaseZeroFlag::test_non_kakita_no_phase_zero_contest_flag`

**Clicktests:**
- `test_school_abilities.py::test_kakita_5th_dan_button_visible_on_dan_5_sheet`
- `test_school_abilities.py::test_kakita_below_5th_dan_hides_button`
- `test_school_abilities.py::test_kakita_5th_dan_button_opens_contest_modal`
- `test_school_abilities.py::test_kakita_5th_dan_modal_defaults_opponent_has_iaijutsu`
- `test_school_abilities.py::test_kakita_5th_dan_opponent_without_iaijutsu_grants_plus_5`
- `test_school_abilities.py::test_kakita_5th_dan_3rd_dan_bonus_applies_with_attacker_phase_0`
- `test_school_abilities.py::test_kakita_5th_dan_roll_applies_bonuses`
- `test_school_abilities.py::test_kakita_5th_dan_damage_scales_up_when_won_by_5`
- `test_school_abilities.py::test_kakita_5th_dan_damage_scales_down_when_lost_by_5`
- `test_school_abilities.py::test_kakita_5th_dan_damage_unchanged_when_diff_under_5`
- `test_school_abilities.py::test_kakita_5th_dan_button_disabled_after_use_until_next_initiative`
- `test_school_abilities.py::test_kakita_5th_dan_modal_cancel_before_roll_does_not_consume`
- `test_school_abilities.py::test_kakita_5th_dan_modal_inherits_4th_dan_damage_bonus`
- `test_school_abilities.py::test_kakita_5th_dan_used_flag_persists_through_reload`
