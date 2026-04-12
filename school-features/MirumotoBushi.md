# Mirumoto Bushi

**School ID:** `mirumoto_bushi`
**Category:** Bushi
**School Ring:** Void - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> Your successful or unsuccessful parries give you a temporary void point.

**Status:** Fully implemented.
- Temporary Void Points are tracked for Mirumoto Bushi (school is in `SCHOOLS_WITH_TEMP_VOID` via the "temporary void" text in the special ability).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Auto-grant of temp VP after parry is implemented.
  - Server: `app/routes/pages.py` passes `mirumoto_temp_vp_on_parry: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` auto-increments temp VP after parry rolls in `runRoll()`.

**Implementation:** `app/game_data.py:982`, `app/game_data.py:2382` (SCHOOLS_WITH_TEMP_VOID membership), `app/routes/pages.py` (mirumoto_temp_vp_on_parry flag), `app/templates/character/sheet.html` (Temp Void counter, auto-grant in runRoll).

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific. General temp void counter tested indirectly via tracking tests.

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

---

## 2nd Dan

> Free raise on parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestCombatFormula::test_mirumoto_bushi_1st_dan_parry_extra_die` - Also validates 2nd Dan: asserts `flat=5` on parry at dan 2 (line 428).

**Clicktests:** None.

---

## 3rd Dan

> At the beginning of each round, you get 2X points, where X is equal to your attack skill. Each point may be spent to decrease the phase of one of your actions by 1 in order to parry, or to provide a bonus of +2 on any type of attack or parry after you have seen your roll.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `mirumoto_round_points: true` and `mirumoto_round_points_max: 2*attack_skill`. Client: tracking section shows a per-round points counter with +/- and Reset. "Spend 3rd Dan Point (+2)" button appears on attack and parry roll results. Points can be spent for +2 flat on the roll.

**Questions (ANSWERED):**
- X = attack skill rank. So 2 * attack_skill points per round.
- Per-round (reset each combat round).
- Points can be spent to lower action phase for a parry OR spent as +2 per point on attack/parry rolls.
- Points can be split between uses within a round.

---

## 4th Dan

> Raise your current and maximum Void by 1. Raising your Void now costs 5 fewer XP. Failed parries against your double attacks do not prevent the automatic serious wound, and against your regular attacks the number of extra rolled damage dice the failed parry reduces is cut in half (rounded down).

**Status:** Fully implemented.
- Ring raise (+1 Void, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Failed parries" modification is implemented.
  - Server: `app/routes/pages.py` passes `mirumoto_parry_modifier: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` in `atkComputeDamage()` - vs double attacks: no parry reduction (auto SW preserved); vs regular attacks: parry reduction halved (rounded down).

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

---

## 5th Dan

> Your void points provide an extra +10 when spent on combat rolls.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `combat_vp_flat_bonus: 10` in void_spend_config when mirumoto_bushi and dan >= 5.
- Client: `app/templates/character/sheet.html` applies +10 per VP flat bonus on attack, wound check, and duel VP spending paths.

**Questions (ANSWERED):**
- The +10 is IN ADDITION to the normal +1k1 from void points. So each VP = +1k1 + 10 flat.
- "Combat rolls" includes wound checks (still need to confirm with user which specific roll types qualify).
- Does this apply to temporary void points as well?

No unit test for the pages.py flag (it's a template context variable), but the behavior is tested through the UI.

---

## Test References

- `tests/test_dice.py:364` - Uses `mirumoto_bushi` to test 1st Dan extra die on parry/double_attack.
- `tests/test_dice.py:417` - Directly tests Mirumoto 1st Dan parry extra die and 2nd Dan free raise.
- `tests/e2e/test_school_selection.py:48` - Uses `mirumoto_bushi` to test that school knack controls appear (counterattack, double_attack, iaijutsu).
- `tests/e2e/test_sheet_js_errors.py:16` - Includes `mirumoto_bushi` in the JS error check suite (Void school ring, counterattack knack, temp void).
- `tests/e2e/test_sheet_display.py:290` - Uses `mirumoto_bushi` for the school knack expansion rules text test.
