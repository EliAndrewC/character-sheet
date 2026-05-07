# Shugenja

**School ID:** `shugenja`
**Category:** Spellcaster
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** commune, pontificate, spellcasting - Commune is rollable (varies by element). Pontificate is rollable with whichever of Water or Air is higher at roll time. Spellcasting is rollable (varies by element).

**DISABLED IN UI:** The Shugenja school is currently disabled in the school selection dropdown with "(not yet implemented)" label. See `app/templates/character/edit.html:117`.

---

## Special Ability

> Your maximum number of void points is equal to your highest ring plus your school rank. You regain a number of void points equal to your lowest Ring after a full night's rest, and one void point per 2 hours for a partial night. However, you may not spend more void points on any one roll than your lowest Ring minus 1.

**Status:** Fully implemented (same as Isawa Ishi). Spellcasting UI and enabling the school in the dropdown are deferred until the school is enabled.
- VP max (highest ring + school rank) is implemented in `game_data.py:872-873` via `void_points_max_shugenja()`. `app/routes/pages.py` uses `void_points_max_shugenja()` for Shugenja VP max display.
- VP spend cap (`min(rings) - 1`) is computed in `app/routes/pages.py` for shugenja/isawa_ishi schools.
- VP regen (lowest ring per night) is implemented in `game_data.py:882-884` via `void_regen_per_night_shugenja()`.

**Implementation:**
- `app/routes/pages.py` (VP max via `void_points_max_shugenja()`, spend cap via `min(rings) - 1`)
- `app/game_data.py:872-873` (`void_points_max_shugenja`)
- `app/game_data.py:882-884` (`void_regen_per_night_shugenja`)
- `app/game_data.py:887-889` (`void_spend_cap_shugenja`)

**Unit tests:**
- `test_game_data_helpers.py:58` - `test_shugenja_max` verifies VP max = highest ring + school rank
- `test_game_data_helpers.py:66` - `test_shugenja_regen` verifies VP regen = lowest ring
- `test_game_data_helpers.py:70` - `test_shugenja_spend_cap` verifies spend cap = min(rings) - 1

**Clicktests:** None (school is disabled in UI).

---

## 1st Dan

> Roll one extra die when rolling precepts or with commune and spellcasting for your chosen element.

**Status:** Fully implemented via technique_choices.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES` (choices are player-selected, not hardcoded).
- Server: `app/models.py` stores player choices in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +1 rolled die for chosen skills.
- Editor UI allows selecting skills.

**Implementation:** `app/game_data.py:2172` (`first_dan_extra_die: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_extra_die`
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_no_choice_no_bonus`

**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] Clicktest for 1st Dan element selection (after enabling school)

---

## 2nd Dan

> You get a free raise when rolling precepts or with commune and spellcasting for your chosen element.

**Status:** Fully implemented via technique_choices.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` (choice is player-selected, not hardcoded).
- Server: `app/models.py` stores player choice in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +5 flat bonus for the chosen skill.
- Editor UI allows selecting skill.

**Implementation:** `app/game_data.py:2173` (`second_dan_free_raise: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_second_dan_free_raise`

**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] Clicktest for 2nd Dan element selection (after enabling school)

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your precepts skill, which may be applied to the following rolls: bragging, intimidation, precepts, tact, wound checks, and spellcasting for your chosen element. You may not spend more than X of these free raises on any single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`. Element restriction on spellcasting free raises is deferred until the school is enabled.
- `source_skill: "precepts"`
- `applicable_to: ["bragging", "intimidation", "precepts", "tact", "wound_check", "spellcasting"]`
- `formula: "2X"`, `max_per_roll: "X"`
- Note: The "for element" restriction on spellcasting is not encoded; spellcasting is listed unconditionally.

**Implementation:** `app/game_data.py:2174-2183` (third_dan dict).

**Unit tests:** None specific to Shugenja 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] Clicktest for Shugenja-specific 3rd Dan applicable skills (after enabling school)

---

## 4th Dan

> Raise your current and maximum Ring of your chosen element by 1. Raising that Ring now costs 5 fewer XP. You may cast one spell per round as an interrupt action.

**Status:** Partially implemented. Ring raise is fully implemented; "cast one spell per round as an interrupt action" is out of scope (combat-phase tracking).
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring (which represents the chosen element).

**Unit tests:** None.
**Clicktests:** None (school is disabled in UI).

---

## 5th Dan

> Your non-Void rings are all considered 1 higher when rolling commune and spellcasting.

**Status:** Fully implemented.
- Server: `app/services/dice.py:build_knack_formula()` adds +1 to non-Void ring values when computing commune and spellcasting formulas for shugenja at 5th Dan.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_shugenja_5th_dan_commune_ring_boost`
- `test_dice.py::TestSchoolAbilities::test_shugenja_5th_dan_spellcasting_ring_boost`
- `test_dice.py::TestSchoolAbilities::test_shugenja_5th_dan_void_not_boosted`
- `test_dice.py::TestSchoolAbilities::test_shugenja_below_5th_dan_no_boost`

**Missing:**
- [ ] Clicktest for ring bonus display (after enabling school)
