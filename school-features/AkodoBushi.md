# Akodo Bushi

**School ID:** `akodo_bushi`
**Category:** Bushi
**School Ring:** Water - Confirmed correct.
**School Knacks:** double_attack, feint, iaijutsu - All present and rollable.

---

## Special Ability

> You gain four temporary void points after a successful feint and one void point after an unsuccessful feint.

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

> Roll an extra die on attack, double attack, and wound check rolls.

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

> Free raise on wound checks.

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

> Excess from wound checks divided by 5 adds a bonus to future attack rolls, scaled by attack skill.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- How exactly does the scaling by attack skill work? Is it `floor(excess/5) * attack_skill`?
- Is the bonus per-round or per-combat?
- Does it stack across multiple wound checks?

**Missing:**
- [ ] Implement the 3rd Dan excess-from-wound-checks mechanic
- [ ] Track the accumulated bonus somewhere (per-round state?)
- [ ] Display the bonus on attack rolls when it's active

---

## 4th Dan

> +1 Water; Water ring costs 5 fewer XP to raise; spend void points for free raises on wound checks.

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

> Spend void points after receiving damage to inflict 10 light wounds per void point spent back to attacker (capped by damage taken).

**Status:** NOT implemented. This is a reactive ability triggered after receiving damage.

**Questions:**
- Does this apply to any type of damage or only melee?
- Is there a UI for this, or should it be a button that appears on the wound check result?

**Missing:**
- [ ] Implement the reflective damage mechanic
- [ ] UI for spending void points after taking damage
