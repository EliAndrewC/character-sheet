# Otaku Bushi

**School ID:** `otaku_bushi`
**Category:** Bushi
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> After an attack against you is completely resolved, you may make a lunge attack at your attacker as an interrupt action at the cost of one action die.

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

> Roll one extra die on iaijutsu, lunge, and wound check rolls.

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

> You get a free raise on wound checks.

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

> After you roll damage against an opponent, increase that character's next X action dice this turn by (6 - that character's Fire) min 1, where X is your attack skill, to a maximum of phase 10.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions (ANSWERED):**
- The increase is (6 - target's Fire), minimum 1.
- The increase is applied to the target's next X action dice, where X is the Otaku's attack skill.
- "Maximum of phase 10" means action dice cannot be increased beyond phase 10.

**Missing:**
- [ ] Implement the 3rd Dan action dice increase mechanic
- [ ] Track which attacker's action dice are affected
- [ ] UI for displaying the action dice modification
- [ ] Unit test: Otaku 3rd Dan increases attacker's action dice
- [ ] Clicktest: attack result at 3rd Dan shows attacker action dice increase

---

## 4th Dan

> Raise your current and maximum Fire by 1. Raising your Fire now costs 5 fewer XP. When you lunge, you always roll the extra damage die from using lunge even if your attack is unsuccessfully parried.

**Status:** Partially implemented.
- Ring raise (+1 Fire, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Lunge always rolls an extra damage die even if unsuccessfully parried" is implemented:
  - Server: `app/routes/pages.py` passes `otaku_lunge_extra_die: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` in `atkComputeDamage()`, when lunge is unsuccessfully parried, adds the lunge extra die back after parry reduction.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

**Missing:**
- [ ] Unit test: Otaku 4th Dan lunge damage includes extra die
- [ ] Clicktest: lunge damage at 4th Dan shows extra die even after failed parry

---

## 5th Dan

> After a successful attack or lunge roll, you may decrease the number of rolled damage dice by 10, to a minimum of 2, to automatically deal 1 serious wound to your opponent. You may only do this once per damage roll.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `otaku_trade_dice_for_sw: true` in school_abilities.
- Client: `app/templates/character/sheet.html` shows a "Trade 10 damage dice for 1 automatic serious wound" button in the damage result when rolled >= 12 (ensuring min 2 after trade).

**Missing:**
- [ ] Clicktest: attack result at 5th Dan offers the 10-dice-for-1-SW option

---

## Test References

- No school-specific test references found. Otaku Bushi exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
