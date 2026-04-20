# Shinjo Bushi

**School ID:** `shinjo_bushi`
**Category:** Bushi
**School Ring:** Air - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> Each action you take in combat has a bonus of 2X, where X is the number of phases for which the action die was held.

**Status:** Implemented for attack-type rolls (regular attack, athletics-attack, double_attack, counterattack, lunge) and parry rolls (regular parry and athletics-parry). The phase-bonus picker still does not surface on feint/iaijutsu rolls (those go straight from menu to roll without any action-die-value dependency the player wants to annotate).

**Implementation:**
- Server: `app/services/dice.py` stamps `shinjo_phase_bonus_attack = True` on every attack-type AND parry-type formula (base attack/parry, attack-variant knacks, athletics-attack, athletics-parry) for the `shinjo_bushi` school. `app/routes/pages.py` exposes `school_abilities.shinjo_phase_bonus = True`.
- Attack client: the attack modal's pre-roll page renders a phase dropdown (1-10) when the flag is set, an action die is present to spend, AND the initiative warning is NOT firing. The displayed bonus is `2 * max(0, current_phase - die_value)`. `atkHitChance` and `atkAvgAttackRoll` both consume the bonus so the probability chart updates live. `rollAttack()` snapshots the bonus onto the formula (`shinjo_phase_bonus`, `shinjo_phase_bonus_phase`, `shinjo_phase_bonus_die_value`) so the post-roll breakdown can label it.
- Parry client: the parry result modal captures the spent action die's value at roll time (`_captureShinjoParryDieValue` inside `executeRoll` / `executeRollWithExtraFlat`), then renders a phase dropdown in the "done" panel. Picking a phase invokes `_applyShinjoParryBonus`, which adjusts `baseTotal` by the delta and stamps `shinjo_phase_bonus`/`shinjo_phase_bonus_phase`/`shinjo_phase_bonus_die_value` onto the formula; the breakdown line re-uses the same metadata as the attack path. Asked post-roll (not pre-roll) because a parry has no hit-probability chart that would need to update live.
- Die selection: when opening the attack through an action-die menu, the bonus uses the clicked die's value (via `_preSpentDieIndex`); otherwise it uses the lowest unspent eligible die (respecting `athletics_only` for athletics-attack). Parry rolls read the die from `_actionDieSpentIndex` after `_autoSpendActionDie` runs.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_shinjo_special_ability_attack_flag`
- `test_dice.py::TestSchoolAbilities::test_shinjo_special_ability_parry_flag`
- `test_dice.py::TestSchoolAbilities::test_shinjo_special_ability_attack_knack_flag`
- `test_dice.py::TestSchoolAbilities::test_shinjo_special_ability_non_attack_knack_no_flag`
- `test_dice.py::TestSchoolAbilities::test_shinjo_special_ability_athletics_attack_flag`
- `test_dice.py::TestSchoolAbilities::test_shinjo_special_ability_flag_only_for_shinjo_school`

**Clicktests:**
- `test_school_abilities.py::test_shinjo_phase_bonus_hidden_without_initiative`
- `test_school_abilities.py::test_shinjo_phase_bonus_hidden_out_of_dice`
- `test_school_abilities.py::test_shinjo_phase_bonus_visible_with_action_dice`
- `test_school_abilities.py::test_shinjo_phase_bonus_applied_to_attack_roll`
- `test_school_abilities.py::test_shinjo_phase_bonus_shifts_probability_chart`
- `test_school_abilities.py::test_shinjo_phase_bonus_uses_clicked_die`
- `test_school_abilities.py::test_shinjo_phase_bonus_on_parry_result_modal`
- `test_school_abilities.py::test_shinjo_phase_bonus_parry_picker_hidden_for_non_shinjo`

---

## 1st Dan

> Roll one extra die on initiative, parry, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["initiative", "parry", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` for parry.
- Initiative extra die applied in `build_initiative_formula()` (checks `"initiative"` in `first_dan_extra_die`).
- Wound check extra die applied in `build_wound_check_formula()` (checks `"wound_check"` in `first_dan_extra_die`).

**Unit tests:**
- `test_dice.py::TestInitiativeAndFlags::test_shinjo_1st_dan_initiative_extra_die`
- `test_dice.py::TestInitiativeAndFlags::test_shinjo_1st_dan_parry_extra_die`
- `test_dice.py::TestInitiativeAndFlags::test_shinjo_1st_dan_wound_check_extra_die`
- `test_dice.py::TestInitiativeAndFlags::test_shinjo_1st_dan_double_attack_no_longer_gets_extra_die`

**Clicktests:**
- `test_school_abilities.py::test_shinjo_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the Shinjo 2nd Dan free raise on parry.
**Clicktests:**
- `test_school_abilities.py::test_shinjo_2nd_dan_parry_bonus`

---

## 3rd Dan

> After a successful or unsuccessful parry, all your action dice are decreased by X, where X is equal to your attack skill. Action dice are considered to have been held since their newly lowered value. This can lower dice to negative numbers.

**Status:** Fully implemented.

**Implementation:**
- Server: `app/routes/pages.py` exposes `school_abilities.shinjo_3rd_dan_parry_decrement = attack_skill` (non-zero only when `shinjo_bushi` + Dan >= 3).
- Client: the dice roller's post-parry hook (alongside the Hiruma / Shinjo 5th Dan hooks) decrements every unspent entry in `window._trackingBridge.actionDice` by that amount. Spent dice are untouched. Fires for both `parry` and `athletics:parry`. Dice can go negative by design ("This can lower dice to negative numbers").
- Feeds Special Ability: because the Special Ability computes phases-held from the live die value, the reduced values automatically yield a larger bonus on later attacks this round.

**Questions (ANSWERED):**
- X is the attack skill rank.
- "All your action dice" means all of the Shinjo's own remaining action dice are decreased.
- "Considered to have been held since their newly lowered value" means the Special Ability's +2X bonus applies retroactively to the reduced values.
- "Can lower dice to negative numbers" means there's no minimum.

**Clicktests:**
- `test_school_abilities.py::test_shinjo_3rd_dan_parry_decrements_unspent_dice`
- `test_school_abilities.py::test_shinjo_below_3rd_dan_no_parry_decrement`

---

## 4th Dan

> Raise your current and maximum Air by 1. Raising your Air now costs 5 fewer XP. Your highest action die is set to 1 at the beginning of each combat round.

**Status:** Fully implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Highest action die set to 1" is implemented:
  - `app/services/dice.py:500` sets `shinjo_4th_dan = school_id == "shinjo_bushi" and dan >= 4`.
  - The flag is included in the initiative formula output at `dice.py:513`.
  - `app/templates/character/sheet.html:1880` renders a template block for Shinjo 4th Dan.
  - `app/templates/character/sheet.html:2430` applies the logic client-side: after rolling initiative, the highest action die is set to 1.

**Implementation:** `app/services/dice.py:500,513`, `app/templates/character/sheet.html:1880,2430`.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.
- No test specifically verifies `shinjo_4th_dan` flag in the initiative formula.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).
- `test_school_abilities.py::test_shinjo_4th_dan_initiative_highest_die_1`

---

## 5th Dan

> After you successfully parry, you may add X to a future wound check this combat after seeing your roll, where X is the amount by which your parry roll exceeded its TN.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `shinjo_bank_parry_excess: true` in school_abilities.
- Client: `app/templates/character/sheet.html` shows a "Bank Parry Excess" section after parry rolls with an opponent roll input to compute and bank the excess for future wound checks. Uses the same banked WC excess mechanism as Isawa Duelist 5th Dan.

**Clicktests:**
- `test_school_abilities.py::test_shinjo_5th_dan_parry_excess_wc`

---

## Test References

- No school-specific test references in the test suite. Shinjo Bushi is referenced in `app/services/dice.py:500` for the 4th Dan initiative mechanic and `app/templates/character/sheet.html:1880,2430` for the client-side implementation.
