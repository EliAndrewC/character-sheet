# Akodo Bushi

**School ID:** `akodo_bushi`
**Category:** Bushi
**School Ring:** Water - Confirmed correct.
**School Knacks:** double_attack, feint, iaijutsu - All present and rollable.

---

## Special Ability

> You get four temporary void points after a successful feint and one void point after an unsuccessful feint.

**Status:** Fully implemented.
- Temporary Void Points are tracked for Akodo Bushi (school is in `SCHOOLS_WITH_TEMP_VOID`).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Temp VP grant after feint (4 on success, 1 on failure) is implemented.
  - Server: `app/routes/pages.py` passes `akodo_temp_vp_on_feint: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` shows "Succeeded (+4 temp VP)" and "Failed (+1 temp VP)" buttons after feint rolls.

**Implementation:** `app/game_data.py:893`, `app/services/dice.py` (SCHOOLS_WITH_TEMP_VOID computed in `app/game_data.py`), `app/routes/pages.py` (akodo_temp_vp_on_feint flag), `app/templates/character/sheet.html` (Temp Void counter, feint result buttons).

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific. General temp void counter tested indirectly via tracking tests.

**Missing:**
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

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `akodo_wc_attack_bonus: true` and `akodo_attack_skill` in school_abilities.
- Client: after passing a wound check (in `wcKeepLightWounds()`), computes `floor(margin / 5) * attack_skill` and banks it. Shows banked bonus indicator in attack modal. Applies as flat bonus on next attack via `rollAttack()`.

**Questions (ANSWERED):**
- Formula: `floor((wound_check_roll - light_wounds) / 5) * attack_skill` = a single flat bonus
- Example: 16 light wounds, wound check roll of 35 -> floor((35-16)/5) = 3, times attack skill 4 = +12 bonus
- The bonus is a single-use discretionary bonus applied all-at-once after seeing a future attack roll (attack, double attack, or feint)
- The user decides after seeing the roll whether to apply the entire bonus
- This is NOT per-adventure free raises; it's a one-shot bonus generated from each wound check

**Missing:**
- [ ] Clicktest: Akodo 3rd Dan wound check banks bonus and applies to next attack

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. You may spend void points after rolling a wound check to receive a free raise for each void point spent.

**Status:** Fully implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- VP for free raises on wound checks:
  - Server: `app/routes/pages.py` passes `wc_vp_free_raise: true` in void_spend_config when akodo_bushi and dan >= 4.
  - Client: `app/templates/character/sheet.html` applies +5 per VP flat bonus on wound check VP spending path.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - 7 tests covering the ring raise mechanics
- `test_xp.py` - covers 4th Dan XP discount

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring`
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7`
- Plus 6 additional 4th Dan ring state tests

---

## 5th Dan

> After you take damage, you may spend void points to deal 10 light wounds to the attacker for every void point spent, up to the amount of damage you took.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `akodo_reflect_damage: true` in school_abilities.
- Client: `app/templates/character/sheet.html` shows a "Reflect Damage" section in the wound check result with a VP input and button. Each VP spent deals 10 LW to the attacker (informational - applied on the attacker's sheet manually).

