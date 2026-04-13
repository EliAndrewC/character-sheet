# Isawa Duelist

**School ID:** `isawa_duelist`
**Category:** Duelist
**School Ring:** Water - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> You add your Water instead of Fire to your rolled damage dice.

**Status:** Fully implemented.
- `dice.py:567` sets `damage_ring_name = "Water"` when `school_id == "isawa_duelist"`.
- This causes all damage calculations for the Isawa Duelist to use Water instead of Fire.

**Implementation:** `app/services/dice.py:567` (`damage_ring_name = "Water" if school_id == "isawa_duelist" else "Fire"`).

**Unit tests:** None specific to this mechanic.
**Clicktests:**
- `test_sheet_js_errors.py` includes `isawa_duelist` indirectly (not in the explicit list but referenced generally).
- `test_school_abilities.py::test_isawa_duelist_damage_shows_water`

---

## 1st Dan

> Roll one extra die on double attack, lunge, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "lunge", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Isawa Duelist 1st Dan.
**Clicktests:**
- `test_school_abilities.py::test_isawa_duelist_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on wound checks.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_isawa_duelist_2nd_dan_wound_check_bonus`

---

## 3rd Dan

> After you make any type of attack roll, you may lower your TN to be hit by 5 for the next time that you are attacked this round to get a bonus of 3X on your attack roll, where X is your attack skill. If a successful or unsuccessful parry is made against your attack, you do not suffer the TN penalty.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `isawa_tn_trade: true` and `isawa_tn_trade_bonus: 3*attack_skill` in school_abilities.
- Client: `app/templates/character/sheet.html` shows a checkbox toggle in the attack modal pre-roll phase: "Trade -5 TN to be hit for +3X on this attack." When checked, adds the flat bonus to the attack roll. Note about TN penalty waiver if parried is informational only.

**Clicktests:**
- `test_school_abilities.py::test_isawa_duelist_3rd_dan_tn_trade_toggle`

**Questions (ANSWERED):**
- X is the attack skill rank (as with all bushi 3rd Dan techniques).
- The -5 TN trade happens after making an attack roll (it's a bonus applied to that attack roll).
- If the attack is parried (successfully or not), the TN penalty is waived.

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. Once per round, you may lunge as an interrupt action at the cost of 1 action die.

**Status:** Partially implemented. Ring raise is fully implemented; "lunge as interrupt action once per round" is out of scope (combat-phase tracking).
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.

**Unit tests:** None specific to Isawa Duelist 4th Dan.
**Clicktests:** None.

---

## 5th Dan

> After a successful wound check, you may add X to a future wound check this combat, where X is the amount by which the wound check exceeded the light wound total.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `isawa_bank_wc_excess: true` in school_abilities.
- Client: `app/templates/character/sheet.html` banks wound check excess (margin when passed) via `wcKeepLightWounds()`, and the wound check modal shows an "Apply Banked Excess" button for future wound checks.

**Clicktests:**
- `test_school_abilities.py::test_isawa_duelist_5th_dan_banks_wc_excess`


