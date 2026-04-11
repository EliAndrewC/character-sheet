# Akodo Bushi

**School ID:** `akodo_bushi`
**Category:** Bushi
**School Ring:** Water - Confirmed correct.
**School Knacks:** double_attack, feint, iaijutsu - All present and rollable.

---

## Special Ability

> You get four temporary void points after a successful feint and one void point after an unsuccessful feint.

**Status:** Partially implemented.
- Temporary Void Points are tracked for Akodo Bushi (school is in `SCHOOLS_WITH_TEMP_VOID`).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- However, making a feint roll does NOT automatically grant temporary void points. This requires manual adjustment.

**Implementation:** `app/game_data.py:893`, `app/services/dice.py` (SCHOOLS_WITH_TEMP_VOID computed in `app/game_data.py`), `app/templates/character/sheet.html` (Temp Void counter).

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific. General temp void counter tested indirectly via tracking tests.

**Missing:**
- [ ] After a feint roll resolves, automatically add 4 temp VP on success or 1 on failure
- [ ] Clicktest: Akodo Bushi feint roll adds temp VP

---

## 1st Dan

> Rolls one extra die on attack, double attack, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "double_attack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:**
- `test_dice.py::TestBuildAllRollFormulas::test_wound_check_formula_present` - verifies wound check rolled=5 for Akodo (Water 3 + 1 + 1 from 1st Dan)

**Clicktests:** No school-specific clicktest for Akodo 1st Dan extra die.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/double_attack/wound_check

---

## 2nd Dan

> You get a free raise on wound checks.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None directly testing the Akodo 2nd Dan free raise on wound checks.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Akodo at 2nd Dan gets +5 flat on wound check formula
- [ ] Clicktest: wound check modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> After you exceed the TN of a wound check, divide the difference between your wound check and the damage roll by 5, rounding down. You may add that number multiplied by X to any future attack this combat, where X is your attack skill.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions (ANSWERED):**
- Formula: `floor((wound_check_roll - light_wounds) / 5) * attack_skill` = a single flat bonus
- Example: 16 light wounds, wound check roll of 35 -> floor((35-16)/5) = 3, times attack skill 4 = +12 bonus
- The bonus is a single-use discretionary bonus applied all-at-once after seeing a future attack roll (attack, double attack, or feint)
- The user decides after seeing the roll whether to apply the entire bonus
- This is NOT per-adventure free raises; it's a one-shot bonus generated from each wound check

**Missing:**
- [ ] Implement the 3rd Dan excess-from-wound-checks mechanic
- [ ] Track the accumulated bonus somewhere (per-round state?)
- [ ] Display the bonus on attack rolls when it's active

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. You may spend void points after rolling a wound check to receive a free raise for each void point spent.

**Status:** Partially implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Spend void points for free raises on wound checks" is NOT implemented. This is a unique mechanic where each void point spent on a wound check provides an additional +5 (free raise) on top of the normal +1k1.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - 7 tests covering the ring raise mechanics
- `test_xp.py` - covers 4th Dan XP discount

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring`
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7`
- Plus 6 additional 4th Dan ring state tests

**Missing:**
- [ ] Implement "void points also give free raises on wound checks" for Akodo 4th Dan
- [ ] This should show as an additional +5 per void point in the wound check modal

---

## 5th Dan

> After you take damage, you may spend void points to deal 10 light wounds to the attacker for every void point spent, up to the amount of damage you took.

**Status:** NOT implemented. This is a reactive ability triggered after receiving damage.

**Missing:**
- [ ] Implement the reflective damage mechanic
- [ ] UI for spending void points after taking damage
