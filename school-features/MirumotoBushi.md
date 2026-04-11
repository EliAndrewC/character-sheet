# Mirumoto Bushi

**School ID:** `mirumoto_bushi`
**Category:** Bushi
**School Ring:** Void - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> Your successful or unsuccessful parries give you a temporary void point.

**Status:** Partially implemented.
- Temporary Void Points are tracked for Mirumoto Bushi (school is in `SCHOOLS_WITH_TEMP_VOID` via the "temporary void" text in the special ability).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- However, making a parry roll does NOT automatically grant a temporary void point. This requires manual adjustment.

**Implementation:** `app/game_data.py:982`, `app/game_data.py:2382` (SCHOOLS_WITH_TEMP_VOID membership), `app/templates/character/sheet.html` (Temp Void counter).

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific. General temp void counter tested indirectly via tracking tests.

**Missing:**
- [ ] After a parry roll resolves, automatically add 1 temp VP (regardless of success/failure)
- [ ] Clicktest: Mirumoto Bushi parry roll adds temp VP

---

## 1st Dan

> Roll one extra die on parry, double attack, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["parry", "double_attack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:**
- `test_dice.py::TestSchoolTechniqueBonus::test_school_technique_first_dan_extra_die` - Uses Mirumoto Bushi to set up a dan-1 character (lines 362-369).
- `test_dice.py::TestCombatFormula::test_mirumoto_bushi_1st_dan_parry_extra_die` - Directly tests that a Mirumoto at dan 2 gets +1 rolled die on parry (line 417). Verifies `rolled=5` (parry 2 + Air 2 + 1 from 1st Dan) and `flat=5` (from 2nd Dan free raise).

**Clicktests:** No school-specific clicktest for Mirumoto 1st Dan extra die.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for parry/double_attack/wound_check

---

## 2nd Dan

> Free raise on parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestCombatFormula::test_mirumoto_bushi_1st_dan_parry_extra_die` - Also validates 2nd Dan: asserts `flat=5` on parry at dan 2 (line 428).

**Clicktests:** None.

**Missing:**
- [ ] Clicktest: parry modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> At the start of each round, gain 2X points to decrease action phases for parries or +2 on any attack or parry roll.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- What is X? Is it the Dan level, a knack rank, or something else?
- "Decrease action phases for parries" - does this mean spending points to move a parry earlier in the round?
- "+2 on any attack or parry roll" - is this a flat +2, and can points be split between phase adjustment and roll bonuses?
- Are the 2X points tracked per round? Is there UI for allocating them?

**Missing:**
- [ ] Implement the 3rd Dan round-start points mechanic
- [ ] UI for allocating points between phase decrease and roll bonus
- [ ] Track points per round
- [ ] Unit test: Mirumoto 3rd Dan point allocation
- [ ] Clicktest: round-start point display and allocation

---

## 4th Dan

> +1 Void; Void ring costs 5 fewer XP to raise; failed parries reduce fewer extra damage dice.

**Status:** Partially implemented.
- Ring raise (+1 Void, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Failed parries reduce fewer extra damage dice" is NOT implemented. This modifies the parry failure outcome.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

**Questions:**
- "Reduce fewer extra damage dice" - does this mean when a parry fails, the attacker gets fewer bonus damage dice than normal? How many fewer?

**Missing:**
- [ ] Implement "failed parries reduce fewer extra damage dice" for Mirumoto 4th Dan
- [ ] Display the reduced damage dice effect in parry roll results
- [ ] Unit test: Mirumoto 4th Dan failed parry damage dice reduction
- [ ] Clicktest: failed parry at 4th Dan shows reduced bonus damage dice

---

## 5th Dan

> Void points provide +10 when spent on combat rolls.

**Status:** NOT implemented. This modifies the standard VP spending mechanic (normally +1k1) to instead provide +10 flat on combat rolls.

**Questions:**
- Does this replace the standard +1k1 from VP, or is the +10 in addition to the +1k1?
- Does "combat rolls" include wound checks, or only attack/parry/knack rolls?
- Does this apply to temporary void points as well?

**Missing:**
- [ ] Implement the 5th Dan +10 per VP on combat rolls mechanic
- [ ] Modify the void spending UI to show the enhanced bonus for Mirumoto
- [ ] Unit test: Mirumoto 5th Dan VP spending gives +10 on combat rolls
- [ ] Clicktest: VP spending on combat rolls at 5th Dan shows +10

---

## Test References

- `tests/test_dice.py:364` - Uses `mirumoto_bushi` to test 1st Dan extra die on parry/double_attack.
- `tests/test_dice.py:417` - Directly tests Mirumoto 1st Dan parry extra die and 2nd Dan free raise.
- `tests/e2e/test_school_selection.py:48` - Uses `mirumoto_bushi` to test that school knack controls appear (counterattack, double_attack, iaijutsu).
- `tests/e2e/test_sheet_js_errors.py:16` - Includes `mirumoto_bushi` in the JS error check suite (Void school ring, counterattack knack, temp void).
- `tests/e2e/test_sheet_display.py:290` - Uses `mirumoto_bushi` for the school knack expansion rules text test.
