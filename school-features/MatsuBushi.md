# Matsu Bushi

**School ID:** `matsu_bushi`
**Category:** Bushi
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> You always roll 10 dice when rolling initiative, keeping the usual number as action dice.

**Status:** Fully implemented.
- `app/services/dice.py:487-489` checks `school_id == "matsu_bushi"` and sets `rolled = 10` in `build_initiative_formula()`.
- The kept dice remain `Void` (unchanged), only rolled is overridden.
- Matsu Bushi is NOT in `SCHOOLS_WITH_TEMP_VOID` (no feint knack, no temporary void mentions).

**Implementation:** `app/game_data.py:1006`, `app/services/dice.py:487-489`.

**Unit tests:** None. No test in `test_dice.py` verifies the Matsu initiative override.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Matsu Bushi initiative formula has `rolled=10` regardless of Void ring
- [ ] Clicktest: initiative roll on the sheet shows 10 rolled dice for Matsu Bushi

---

## 1st Dan

> Roll one extra die on double attack, iaijutsu, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "iaijutsu", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Matsu 1st Dan extra die (tested generically via other schools in `test_dice.py`).
**Clicktests:** None school-specific.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for double_attack/iaijutsu/wound_check

---

## 2nd Dan

> You get a free raise on iaijutsu rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "iaijutsu"`
- Applied as +5 flat bonus on iaijutsu rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the Matsu 2nd Dan free raise on iaijutsu.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Matsu at 2nd Dan gets +5 flat on iaijutsu formula
- [ ] Clicktest: iaijutsu modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> When you spend a void point, you may add 3X to any future wound check this combat after seeing the roll, where X is your attack skill.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `matsu_vp_wc_bonus: true` and `matsu_vp_wc_amount: 3*attack_skill` in school_abilities.
- Client: `app/templates/character/sheet.html` banks 3*attack_skill per VP spent via `deductVoidPoints()`, and the wound check modal shows an "Apply Matsu Bonus" button to apply the full banked amount after seeing the roll.

**Questions (ANSWERED):**
- X = the Matsu's attack skill rank. So spending 1 VP adds 3 * attack_skill to a wound check.
- "After seeing the roll" = yes, VP can be spent retroactively after seeing the wound check result.
- Remaining question: can multiple VP be spent on a single wound check? (Each adding 3X?)

**Missing:**
- [ ] Unit test: Matsu 3rd Dan VP spending adds 3X to wound check
- [ ] Clicktest: wound check result offers VP spending option at 3rd Dan

---

## 4th Dan

> Raise your current and maximum Fire by 1. Raising your Fire now costs 5 fewer XP. When you miss the TN on a double attack roll by less than 20, you are still considered to have hit, but you deal no extra damage.

**Status:** Fully implemented.
- Ring raise (+1 Fire, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Near-misses on double attacks still hit with no bonus damage" is implemented:
  - Server: `app/routes/pages.py` passes `matsu_near_miss: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` treats double attack rolls that miss by less than 20 as hits with 0 extra damage dice, showing "NEAR-MISS HIT" in the result display.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

**Missing:**
- [ ] Unit test: Matsu 4th Dan double attack near-miss converts to hit
- [ ] Clicktest: double attack near-miss at 4th Dan shows hit with no bonus damage

---

## 5th Dan

> After you deal light wounds which result in the defender taking one or more serious wounds, their light wound total is reset to 15 instead of 0.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `matsu_lw_reset_15: true` in school_abilities.
- Client: `app/templates/character/sheet.html` shows an informational note in the damage result: "If this causes serious wounds, the defender's light wounds reset to 15 instead of 0." This is a display-only implementation since the defender's sheet is separate.

**Missing:**
- [ ] Unit test: Matsu 5th Dan sets defender's light wounds to 15 after dealing serious wounds
- [ ] Clicktest: dealing serious wounds at 5th Dan shows light wound reset to 15

---

## Test References

- No school-specific test references found. Matsu Bushi is only referenced in `app/services/dice.py:487` for the initiative override.
