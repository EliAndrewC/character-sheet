# Yogo Warden

**School ID:** `yogo_warden`
**Category:** Bushi
**School Ring:** Earth - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, feint - All present and rollable.

---

## Special Ability

> Gain a temporary void point every time you take a serious wound.

**Status:** Fully implemented.
- Temporary Void Points are tracked for Yogo Warden (school is in `SCHOOLS_WITH_TEMP_VOID` via two mechanisms: the "temporary void" text in the special ability at `app/game_data.py`, and the feint knack check at `app/game_data.py`).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Auto-grant of temp VP on serious wound is implemented.
  - Server: `app/routes/pages.py` passes `yogo_temp_vp_on_sw: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` auto-increments temp VP in `applyWoundCheckFailure()` and `wcTakeSeriousAndReset()` when serious wounds are gained.

**Implementation:** `app/game_data.py`, `app/game_data.py` (SCHOOLS_WITH_TEMP_VOID membership), `app/routes/pages.py` (yogo_temp_vp_on_sw flag), `app/templates/character/sheet.html` (Temp Void counter, auto-grant in wound check functions).

---

## Temp Void Tracking (Feint)

**Status:** Fully implemented.
- Yogo Warden also has the feint knack, so temp void tracking is doubly applicable.
- The feint knack's 1 temp VP is granted by the server only on a SUCCESSFUL feint (met the TN entered in the feint modal, not parried) - `feint_success_temp_vp`. Before 2026-10-03 it was granted on every feint.

---

## 1st Dan

> Roll one extra die on attack, damage, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "damage", "wound_check"]`
- Attack extra die: applied in `app/services/dice.py:_apply_school_technique_bonus()`.
- Wound check extra die: applied in `build_wound_check_formula()`.
- Damage extra die: implemented via school-specific code in `app/services/dice.py` damage section.

**Questions (ANSWERED):**
- Yes, the "damage" extra die adds +1k0 (one extra rolled die) to all damage rolls. This needs school-specific handling in the damage formula builder since the generic `_apply_school_technique_bonus()` is not called for damage rolls. Same applies to Kuni Witch Hunter.

---

## 2nd Dan

> You get a free raise on wound checks.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

---

## 3rd Dan

> Whenever you spend a void point, reduce your current light wound total by 2X, where X is your attack skill.

**Status:** Fully implemented (server-side).
- `void_spend.spend_consequences()` defines `yogo_vp_heal_amount` (2 x attack); `apply_void_spend()` takes it off the character for every void point spent, on any roll.
- **Wound checks: the heal comes off BEFORE the check** (fixed 2026-10-12; the check used to be judged against the light wounds from before the spend). `wound_checks.build_wound_check(void=...)` lowers the check's `light_wounds` for pre-roll void and stamps `yogo_lw_before` / `yogo_lw_healed`; a post-roll `wc_vp` point records its `healed` amount on the session action, `_wc_state` subtracts it, and undo puts it back on the character. A simulated (read-only) roll heals the scenario amount, never the character.
- Sheet: the wound check modal's TN follows the selected void (`_wcLwAfterVoid`), the result adopts the server's `light_wounds`, and a "Yogo 3rd Dan: void points lowered light wounds by N (A to B)" line appears in the result and on the copy-as-image card.
- Tests: `tests/test_wound_check_rolls.py::test_yogo_*`, `test_4th_dan_void_raise_on_wound_checks`; clicktest `test_school_abilities.py::test_yogo_pre_roll_void_lowers_light_wounds_before_the_wound_check`.

**Questions (ANSWERED):**
- X is the attack skill rank (as with all bushi 3rd Dan techniques).
- This triggers whenever a void point is spent (any usage), not just as a standalone action.
- Light wound total can presumably be reduced to 0 but not below.

---

## 4th Dan

> Raise your current and maximum Earth by 1.  Raising your Earth now costs 5 fewer XP.  You get an extra free raise for each void point you spend on wound checks.

**Status:** Fully implemented.
- Ring raise (+1 Earth, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- VP for extra free raise on wound checks - EVERY void point, pre-roll and post-roll:
  - Pre-roll: `wound_check_flags()["yogo_wc_vp_free_raise"]`; `build_wound_check` adds a "Yogo 4th Dan (N void points spent)" +5 each bonus row (fixed 2026-10-12: only the probability preview used to include it). Deliberately separate from `wc_vp_free_raise`, which Akodo 4th Dan shares and which is post-roll only ("after making any combat roll").
  - Post-roll: the `wc_vp` session action (+5 each), shared with Akodo 4th Dan.

---

## 5th Dan

> TBD

**Status:** NOT implemented. The 5th Dan technique text is marked as "TBD" in the game data.

**Missing:**
- [ ] Awaiting rules release for 5th Dan technique

---

## Test References

- No school-specific test references found in the test suite. Yogo Warden exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.

## Archery

On an arrow, 1st Dan's extra rolled damage die counts as 5 more excess for the damage bands instead of a die (GM, archery-design Q3). See `archery-design/design.md`.
