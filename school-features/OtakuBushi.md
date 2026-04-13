# Otaku Bushi

**School ID:** `otaku_bushi`
**Category:** Bushi
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> After an attack against you is completely resolved, you may make a lunge attack at your attacker as an interrupt action at the cost of one action die.

**Status:** Out of scope - requires combat-phase tracking (interrupt lunge costing 1 action die).

**Implementation:** `app/game_data.py:1032` (definition only). No corresponding logic in `dice.py` or templates.

**Unit tests:** None.
**Clicktests:** None.

---

## 1st Dan

> Roll one extra die on iaijutsu, lunge, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["iaijutsu", "lunge", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Otaku 1st Dan extra die (tested generically via other schools in `test_dice.py`).
**Clicktests:**
- `test_school_abilities.py::test_otaku_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on wound checks.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None directly testing the Otaku 2nd Dan free raise on wound checks.
**Clicktests:**
- `test_school_abilities.py::test_otaku_2nd_dan_wound_check_bonus`

---

## 3rd Dan

> After you roll damage against an opponent, increase that character's next X action dice this turn by (6 - that character's Fire) min 1, where X is your attack skill, to a maximum of phase 10.

**Status:** Out of scope - requires tracking opponent's action dice and modifying them (cross-character combat-phase tracking).

**Questions (ANSWERED):**
- The increase is (6 - target's Fire), minimum 1.
- The increase is applied to the target's next X action dice, where X is the Otaku's attack skill.
- "Maximum of phase 10" means action dice cannot be increased beyond phase 10.

---

## 4th Dan

> Raise your current and maximum Fire by 1. Raising your Fire now costs 5 fewer XP. When you lunge, you always roll the extra damage die from using lunge even if your attack is unsuccessfully parried.

**Status:** Fully implemented.
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
- `test_school_abilities.py::test_otaku_4th_dan_lunge_extra_die`

---

## 5th Dan

> After a successful attack or lunge roll, you may decrease the number of rolled damage dice by 10, to a minimum of 2, to automatically deal 1 serious wound to your opponent. You may only do this once per damage roll.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `otaku_trade_dice_for_sw: true` in school_abilities.
- Client: `app/templates/character/sheet.html` shows a "Trade 10 damage dice for 1 automatic serious wound" button in the damage result when rolled >= 12 (ensuring min 2 after trade).

**Clicktests:**
- `test_school_abilities.py::test_otaku_5th_dan_trade_dice_for_sw`

---

## Test References

- No school-specific test references found. Otaku Bushi exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
