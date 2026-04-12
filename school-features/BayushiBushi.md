# Bayushi Bushi

**School ID:** `bayushi_bushi`
**Category:** Bushi
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, feint, iaijutsu - All present and rollable.

---

## Special Ability

> When spending void points on all types of attack rolls, add 1k1 to the damage rolls of those attacks per void point spent.

**Status:** NOT implemented.
- The damage formula in `build_all_roll_formulas()` does not have any Bayushi-specific logic for adding 1k1 per VP spent on damage.
- The attack modal does not provide a VP-to-damage mechanic for this school.

**Implementation:** `app/game_data.py:927` (definition only). No corresponding logic in `dice.py` or templates.

**Unit tests:** None specific to the +1k1 per VP spent damage mechanic.
**Clicktests:** None.

**Missing:**
- [ ] Implement +1k1 per VP spent on damage rolls in the attack/damage modal
- [ ] Unit test: Bayushi Bushi damage formula reflects +1k1 per VP spent
- [ ] Clicktest: Bayushi Bushi attack modal offers VP spending for bonus damage dice

---

## Temp Void Tracking

**Status:** Partially implemented.
- Bayushi Bushi has the feint knack, so it is included in `SCHOOLS_WITH_TEMP_VOID` via the feint-knack check in `app/game_data.py:2385`.
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Feint rolls do NOT automatically grant temporary void points; manual adjustment is required.

**Implementation:** `app/game_data.py:2385` (SCHOOLS_WITH_TEMP_VOID membership), `app/templates/character/sheet.html` (Temp Void counter).

---

## 1st Dan

> Roll one extra die on iaijutsu, double attack, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["iaijutsu", "double_attack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Bayushi 1st Dan extra die (tested generically via Akodo in `test_dice.py`).
**Clicktests:** None school-specific.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for iaijutsu/double_attack/wound_check

---

## 2nd Dan

> You get a free raise on double attack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "double_attack"`
- Applied as +5 flat bonus on double attack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the Bayushi 2nd Dan free raise on double attack.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Bayushi at 2nd Dan gets +5 flat on double attack formula
- [ ] Clicktest: double attack modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Your feints do Xk1 damage, where X is your attack skill. You don't roll extra damage dice from your Fire or from exceeding the TN, but your Special Ability may increase the damage.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions (ANSWERED):**
- Damage formula: (attack_skill)k1 with NO extra damage from ring or TN excess.
- However, the Bayushi special ability (+1k1 per VP spent on the roll) DOES apply. So if attack=4 and 1 VP spent on the feint: damage = 5k2.
- This is a separate damage roll triggered after a successful feint.

**Missing:**
- [ ] Implement the 3rd Dan feint-deals-damage mechanic
- [ ] Display feint damage information in the feint roll result
- [ ] Unit test: Bayushi 3rd Dan feint rolls include damage
- [ ] Clicktest: feint roll at 3rd Dan shows damage output

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

**Missing:**
- [ ] Clicktest: attack roll after feint at 4th Dan shows the free raise bonus

---

## 5th Dan

> When you fail a wound check, calculate your serious wounds as if you had half your number of light wounds.

**Status:** Fully implemented.
- Server: `app/services/dice.py:build_wound_check_formula()` sets `bayushi_5th_dan_half_lw: True` flag.
- Client: `app/templates/character/sheet.html` uses `Math.floor(lw / 2)` for serious wound calculation when flag is set.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_bayushi_5th_dan_half_lw_flag`
- `test_dice.py::TestSchoolAbilities::test_bayushi_below_5th_dan_no_half_lw_flag`

**Clicktests:** None.

**Missing:**
- [ ] Clicktest: wound check failure at 5th Dan shows reduced serious wounds

---

## Test References

- `tests/test_routes.py:70` - Uses `bayushi_bushi` as the school for a view character test.
- `tests/test_models.py:63` - Uses `bayushi_bushi` in `Character.from_dict` test.
- `tests/test_versions.py:102` - Uses `bayushi_bushi` in a school-change diff test.
- `tests/e2e/test_edit_character.py:15` - Uses `bayushi_bushi` as the school when creating a character in autosave tests.
