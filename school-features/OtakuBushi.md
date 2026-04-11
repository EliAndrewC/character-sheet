# Otaku Bushi

**School ID:** `otaku_bushi`
**Category:** Bushi
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> Make a lunge attack at your attacker as an interrupt action at the cost of one action die.

**Status:** NOT implemented.
- No code in `dice.py` or templates modifies lunge behavior for Otaku Bushi.
- The interrupt-for-1-die mechanic is not tracked anywhere.
- Otaku Bushi is NOT in `SCHOOLS_WITH_TEMP_VOID` (no feint knack, no temporary void mentions).

**Implementation:** `app/game_data.py:1032` (definition only). No corresponding logic in `dice.py` or templates.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement the interrupt lunge mechanic (1 action die cost)
- [ ] UI indicator on the sheet showing this ability is available
- [ ] Unit test: Otaku Bushi lunge as interrupt action
- [ ] Clicktest: lunge action shows the 1-die interrupt cost

---

## 1st Dan

> Roll an extra die on iaijutsu, lunge, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["iaijutsu", "lunge", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Otaku 1st Dan extra die (tested generically via other schools in `test_dice.py`).
**Clicktests:** None school-specific.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for iaijutsu/lunge/wound_check

---

## 2nd Dan

> Free raise on wound checks.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None directly testing the Otaku 2nd Dan free raise on wound checks.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Otaku at 2nd Dan gets +5 flat on wound check formula
- [ ] Clicktest: wound check modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Increase attacker's next action dice by (6 - Fire) minimum 1, scaled by attack skill, maximum phase 10.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- "Scaled by attack skill" - does this mean the increase is `(6 - Fire) * attack_skill`?
- Is this triggered after a successful lunge (interrupt), or after any attack?
- "Maximum phase 10" - the attacker's action die cannot exceed 10 after the increase?

**Missing:**
- [ ] Implement the 3rd Dan action dice increase mechanic
- [ ] Track which attacker's action dice are affected
- [ ] UI for displaying the action dice modification
- [ ] Unit test: Otaku 3rd Dan increases attacker's action dice
- [ ] Clicktest: attack result at 3rd Dan shows attacker action dice increase

---

## 4th Dan

> +1 Fire; Fire ring costs 5 fewer XP to raise; lunge always rolls an extra damage die even if unsuccessfully parried.

**Status:** Partially implemented.
- Ring raise (+1 Fire, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Lunge always rolls an extra damage die even if unsuccessfully parried" is NOT implemented. This requires modifying the lunge damage formula when the lunge is parried.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

**Missing:**
- [ ] Implement "lunge extra damage die on unsuccessful parry" for Otaku 4th Dan
- [ ] Modify lunge damage formula to include the bonus die
- [ ] Unit test: Otaku 4th Dan lunge damage includes extra die
- [ ] Clicktest: lunge damage at 4th Dan shows extra die even after failed parry

---

## 5th Dan

> After a successful attack, spend 10 dice to automatically deal 1 serious wound; once per damage roll.

**Status:** NOT implemented. This is a unique mechanic that converts excess dice into an automatic serious wound.

**Questions:**
- "Spend 10 dice" - does this mean 10 of the damage dice are removed, or 10 action dice?
- Is this in addition to normal damage, or instead of rolling those 10 dice for damage?
- "Once per damage roll" - can this only be used once per attack?

**Missing:**
- [ ] Implement the 5th Dan automatic serious wound mechanic
- [ ] UI for choosing to spend 10 dice for the auto-wound
- [ ] Unit test: Otaku 5th Dan dice-to-wound conversion
- [ ] Clicktest: attack result at 5th Dan offers the 10-dice-for-1-SW option

---

## Test References

- No school-specific test references found. Otaku Bushi exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
