# Yogo Warden

**School ID:** `yogo_warden`
**Category:** Bushi
**School Ring:** Earth - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, feint - All present and rollable.

---

## Special Ability

> Gain a temporary void point every time you take a serious wound.

**Status:** Partially implemented.
- Temporary Void Points are tracked for Yogo Warden (school is in `SCHOOLS_WITH_TEMP_VOID` via two mechanisms: the "temporary void" text in the special ability at `app/game_data.py:2382`, and the feint knack check at `app/game_data.py:2385`).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- However, taking a serious wound does NOT automatically grant a temporary void point. This requires manual adjustment.

**Implementation:** `app/game_data.py:1088`, `app/game_data.py:2382-2386` (SCHOOLS_WITH_TEMP_VOID membership), `app/templates/character/sheet.html` (Temp Void counter).

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific. General temp void counter tested indirectly via tracking tests.

**Missing:**
- [ ] After taking a serious wound, automatically add 1 temp VP
- [ ] Clicktest: Yogo Warden serious wound grants temp VP

---

## Temp Void Tracking (Feint)

**Status:** Partially implemented.
- Yogo Warden also has the feint knack, so temp void tracking is doubly applicable.
- Feint rolls do NOT automatically grant temporary void points; manual adjustment is required.

---

## 1st Dan

> Roll one extra die on attack, damage, and wound check rolls.

**Status:** Partially implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "damage", "wound_check"]`
- Attack extra die: applied in `app/services/dice.py:_apply_school_technique_bonus()`.
- Wound check extra die: applied in `build_wound_check_formula()`.
- Damage extra die: The `"damage"` entry is present in the bonus list, but `_apply_school_technique_bonus()` is not called during damage formula construction. Damage formulas are built inline in `build_all_roll_formulas()` and only check for specific school IDs (courtier, brotherhood_of_shinsei_monk). There is no generic mechanism to apply 1st Dan extra die to damage rolls.

**Unit tests:** None specific to Yogo Warden 1st Dan.
**Clicktests:** None school-specific.

**Questions (ANSWERED):**
- Yes, the "damage" extra die adds +1k0 (one extra rolled die) to all damage rolls. This needs school-specific handling in the damage formula builder since the generic `_apply_school_technique_bonus()` is not called for damage rolls. Same applies to Kuni Witch Hunter.

**Missing:**
- [ ] Implement +1k0 on all damage rolls for Yogo Warden (school-specific code in damage formula builder)
- [ ] Unit test: Yogo Warden 1st Dan gets +1 rolled die on attack, damage, and wound check
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/damage/wound_check

---

## 2nd Dan

> You get a free raise on all wound check rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None directly testing the Yogo Warden 2nd Dan free raise on wound checks.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Yogo Warden at 2nd Dan gets +5 flat on wound check formula
- [ ] Clicktest: wound check modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Whenever you spend a void point, reduce your current light wound total by 2X, where X is your attack skill.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions (ANSWERED):**
- X is the attack skill rank (as with all bushi 3rd Dan techniques).
- This triggers whenever a void point is spent (any usage), not just as a standalone action.
- Light wound total can presumably be reduced to 0 but not below.

**Missing:**
- [ ] Implement the 3rd Dan VP-for-light-wound-reduction mechanic
- [ ] UI button on the sheet for spending VP to reduce light wounds
- [ ] Unit test: Yogo Warden 3rd Dan VP spending reduces light wounds by 2X
- [ ] Clicktest: 3rd Dan VP spending button reduces light wound counter

---

## 4th Dan

> Raise your current and maximum Earth by 1. Raising your Earth now costs 5 fewer XP. You get an extra free raise for each void point you spend on wound check rolls.

**Status:** Partially implemented.
- Ring raise (+1 Earth, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Extra free raise per void point spent on wound checks" is NOT implemented. This means each VP spent on a wound check should provide an additional +5 (free raise) on top of the normal +1k1 benefit.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

**Missing:**
- [ ] Implement "extra free raise per VP on wound checks" for Yogo Warden 4th Dan
- [ ] Display the additional +5 per VP in the wound check modal
- [ ] Unit test: Yogo Warden 4th Dan wound check gets extra +5 per VP spent
- [ ] Clicktest: wound check at 4th Dan shows enhanced VP bonus

---

## 5th Dan

> TBD

**Status:** NOT implemented. The 5th Dan technique text is marked as "TBD" in the game data.

**Missing:**
- [ ] Awaiting rules release for 5th Dan technique

---

## Test References

- No school-specific test references found in the test suite. Yogo Warden exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
