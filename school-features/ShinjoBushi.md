# Shinjo Bushi

**School ID:** `shinjo_bushi`
**Category:** Bushi
**School Ring:** Air - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> Each action you take in combat has a bonus of 2X, where X is the number of phases for which the action die was held.

**Status:** Out of scope - requires combat-phase tracking (tracking how long each action die was held).

**Implementation:** `app/game_data.py:1059` (definition only). No corresponding logic in `dice.py` or templates.

**Unit tests:** None.
**Clicktests:** None.

---

## 1st Dan

> Roll one extra die on double attack, initiative, and parry rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "initiative", "parry"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` for double_attack and parry.
- Initiative extra die applied in `build_initiative_formula()` at `dice.py:492-494` (checks `"initiative"` in `first_dan_extra_die`).
- Note: wound_check is NOT in the 1st Dan list for Shinjo (unlike most bushi schools).

**Unit tests:** None specific to Shinjo 1st Dan (no test verifies the initiative extra die from 1st Dan).
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

**Status:** Out of scope - requires live action die manipulation and combat-phase tracking.

**Questions (ANSWERED):**
- X is the attack skill rank.
- "All your action dice" means all of the Shinjo's own remaining action dice are decreased.
- "Considered to have been held since their newly lowered value" means the Special Ability's +2X bonus applies retroactively to the reduced values.
- "Can lower dice to negative numbers" means there's no minimum.

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
