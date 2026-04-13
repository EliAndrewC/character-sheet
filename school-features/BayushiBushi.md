# Bayushi Bushi

**School ID:** `bayushi_bushi`
**Category:** Bushi
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, feint, iaijutsu - All present and rollable.

---

## Special Ability

> When spending void points on all types of attack rolls, add 1k1 to the damage rolls of those attacks per void point spent.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `bayushi_vp_damage: true` in school_abilities.
- Client: `sheet.html` in `atkComputeDamage()` adds +1 rolled and +1 kept to damage per VP spent on the attack roll (`f.void_spent`).

**Implementation:** `app/game_data.py:927` (definition), `app/routes/pages.py` (bayushi_vp_damage flag), `app/templates/character/sheet.html` (atkComputeDamage).

**Unit tests:** None specific to the +1k1 per VP spent damage mechanic.
**Clicktests:**
- `test_school_abilities.py::test_bayushi_vp_damage_on_attack`

**Missing:**
- [ ] Behavioral clicktest: roll an attack with VP spent, verify damage formula shows +1k1 per VP in the damage breakdown

---

## Temp Void Tracking

**Status:** Fully implemented.
- Bayushi Bushi has the feint knack, so it is included in `SCHOOLS_WITH_TEMP_VOID` via the feint-knack check in `app/game_data.py:2385`.
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- The feint knack temp VP auto-grant (1 VP on successful feint) is now implemented via `feint_temp_vp` flag. Client shows "Feint succeeded (+1 temp VP)" button after feint rolls.

**Implementation:** `app/game_data.py:2385` (SCHOOLS_WITH_TEMP_VOID membership), `app/templates/character/sheet.html` (Temp Void counter, feint_temp_vp grant).

**Clicktests:**
- `test_school_abilities.py::test_feint_temp_vp_button_for_bayushi`

---

## 1st Dan

> Roll one extra die on iaijutsu, double attack, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["iaijutsu", "double_attack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Bayushi 1st Dan extra die (tested generically via Akodo in `test_dice.py`).
**Clicktests:**
- `test_school_abilities.py::test_bayushi_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on double attack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "double_attack"`
- Applied as +5 flat bonus on double attack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the Bayushi 2nd Dan free raise on double attack.
**Clicktests:**
- `test_school_abilities.py::test_bayushi_2nd_dan_double_attack_bonus`

---

## 3rd Dan

> Your feints do Xk1 damage, where X is your attack skill. You don't roll extra damage dice from your Fire or from exceeding the TN, but your Special Ability may increase the damage.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `bayushi_feint_damage: true` and `bayushi_feint_damage_rolled: attack_skill`. Client: `sheet.html` shows "Roll Feint Damage" button after feint rolls. Damage = attack_skill rolled, 1 kept, no ring/TN bonus. Bayushi Special VP bonus (+1k1 per VP) applies to the feint damage.

**Clicktests:**
- `test_school_abilities.py::test_bayushi_3rd_dan_feint_shows_damage`
- `test_school_abilities.py::test_bayushi_feint_damage_button`

**Questions (ANSWERED):**
- Damage formula: (attack_skill)k1 with NO extra damage from ring or TN excess.
- However, the Bayushi special ability (+1k1 per VP spent on the roll) DOES apply. So if attack=4 and 1 VP spent on the feint: damage = 5k2.
- This is a separate damage roll triggered after a successful feint.

---

## 4th Dan

> Raise your current and maximum Fire by 1. Raising your Fire now costs 5 fewer XP. After a successful or unsuccessful feint, you may apply a free raise to any future attack this combat.

**Status:** Fully implemented.
- Ring raise (+1 Fire, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Free raise on any future attack after feint" is implemented.
  - Server: `app/routes/pages.py` passes `bayushi_post_feint_raise: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` shows a "Bank free raise for next attack (+5)" button after feint rolls, and applies the +5 in `rollAttack()`.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic, not Bayushi-specific).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).
- `test_school_abilities.py::test_bayushi_4th_dan_post_feint_raise`

---

## 5th Dan

> When you fail a wound check, calculate your serious wounds as if you had half your number of light wounds.

**Status:** Fully implemented.
- Server: `app/services/dice.py:build_wound_check_formula()` sets `bayushi_5th_dan_half_lw: True` flag.
- Client: `app/templates/character/sheet.html` uses `Math.floor(lw / 2)` for serious wound calculation when flag is set.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_bayushi_5th_dan_half_lw_flag`
- `test_dice.py::TestSchoolAbilities::test_bayushi_below_5th_dan_no_half_lw_flag`

**Clicktests:**
- `test_school_abilities.py::test_bayushi_5th_dan_reduced_serious_wounds`

---

## Test References

- `tests/test_routes.py:70` - Uses `bayushi_bushi` as the school for a view character test.
- `tests/test_models.py:63` - Uses `bayushi_bushi` in `Character.from_dict` test.
- `tests/test_versions.py:102` - Uses `bayushi_bushi` in a school-change diff test.
- `tests/e2e/test_edit_character.py:15` - Uses `bayushi_bushi` as the school when creating a character in autosave tests.
