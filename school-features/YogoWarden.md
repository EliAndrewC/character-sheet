# Yogo Warden

**School ID:** `yogo_warden`
**Category:** Bushi
**School Ring:** Earth - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, feint - All present and rollable.

---

## Special Ability

> Gain a temporary void point every time you take a serious wound.

**Status:** Fully implemented.
- Temporary Void Points are tracked for Yogo Warden (school is in `SCHOOLS_WITH_TEMP_VOID` via two mechanisms: the "temporary void" text in the special ability at `app/game_data.py:2382`, and the feint knack check at `app/game_data.py:2385`).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Auto-grant of temp VP on serious wound is implemented.
  - Server: `app/routes/pages.py` passes `yogo_temp_vp_on_sw: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` auto-increments temp VP in `applyWoundCheckFailure()` and `wcTakeSeriousAndReset()` when serious wounds are gained.

**Implementation:** `app/game_data.py:1088`, `app/game_data.py:2382-2386` (SCHOOLS_WITH_TEMP_VOID membership), `app/routes/pages.py` (yogo_temp_vp_on_sw flag), `app/templates/character/sheet.html` (Temp Void counter, auto-grant in wound check functions).

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific. General temp void counter tested indirectly via tracking tests.

---

## Temp Void Tracking (Feint)

**Status:** Fully implemented.
- Yogo Warden also has the feint knack, so temp void tracking is doubly applicable.
- The feint knack temp VP auto-grant (1 VP on successful feint) is now implemented via `feint_temp_vp` flag. Client shows "Feint succeeded (+1 temp VP)" button after feint rolls.

---

## 1st Dan

> Roll one extra die on attack, damage, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "damage", "wound_check"]`
- Attack extra die: applied in `app/services/dice.py:_apply_school_technique_bonus()`.
- Wound check extra die: applied in `build_wound_check_formula()`.
- Damage extra die: implemented via school-specific code in `app/services/dice.py` damage section.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_yogo_warden_1st_dan_damage_extra_die` - verifies +1k0 on damage rolls
**Clicktests:** None school-specific.

**Questions (ANSWERED):**
- Yes, the "damage" extra die adds +1k0 (one extra rolled die) to all damage rolls. This needs school-specific handling in the damage formula builder since the generic `_apply_school_technique_bonus()` is not called for damage rolls. Same applies to Kuni Witch Hunter.

---

## 2nd Dan

> You get a free raise on all wound check rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None directly testing the Yogo Warden 2nd Dan free raise on wound checks.
**Clicktests:** None.

---

## 3rd Dan

> Whenever you spend a void point, reduce your current light wound total by 2X, where X is your attack skill.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `yogo_vp_heals_lw: true` and `yogo_vp_heal_amount: 2*attack_skill` in school_abilities.
- Client: `app/templates/character/sheet.html` hooks into `deductVoidPoints()` to automatically reduce light wounds by 2*attack_skill per VP spent.

**Questions (ANSWERED):**
- X is the attack skill rank (as with all bushi 3rd Dan techniques).
- This triggers whenever a void point is spent (any usage), not just as a standalone action.
- Light wound total can presumably be reduced to 0 but not below.

---

## 4th Dan

> Raise your current and maximum Earth by 1. Raising your Earth now costs 5 fewer XP. You get an extra free raise for each void point you spend on wound check rolls.

**Status:** Fully implemented.
- Ring raise (+1 Earth, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- VP for extra free raise on wound checks:
  - Server: `app/routes/pages.py` passes `wc_vp_free_raise: true` in void_spend_config when yogo_warden and dan >= 4 (same pattern as Akodo 4th Dan).
  - Client: `app/templates/character/sheet.html` applies +5 per VP flat bonus on wound check VP spending path.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

---

## 5th Dan

> TBD

**Status:** NOT implemented. The 5th Dan technique text is marked as "TBD" in the game data.

**Missing:**
- [ ] Awaiting rules release for 5th Dan technique

---

## Test References

- No school-specific test references found in the test suite. Yogo Warden exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
