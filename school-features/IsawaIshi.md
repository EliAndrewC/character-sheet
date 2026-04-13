# Isawa Ishi

**School ID:** `isawa_ishi`
**Category:** Spellcaster
**School Ring:** Void - Confirmed correct.
**School Knacks:** absorb_void, kharmic_spin, otherworldliness - Absorb_void is rollable (Void). Kharmic_spin is rollable (Void). Otherworldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Your maximum number of void points is equal to your highest ring plus your school rank. You regain a number of void points equal to your lowest Ring after a full night's rest, and one void point per 2 hours for a partial night. However, you may not spend more void points on any one roll than your lowest Ring minus 1.

**Status:** Fully implemented.
- VP max (highest ring + school rank) is implemented in `game_data.py:872-873` via `void_points_max_shugenja()`. `app/routes/pages.py` uses `void_points_max_shugenja()` for Isawa Ishi VP max display.
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

**Clicktests:**
- `test_sheet_js_errors.py:19` includes `isawa_ishi` in the sheet JS error check list.
- `test_school_abilities.py::test_isawa_ishi_vp_max_display`
- `test_school_abilities.py::test_isawa_ishi_vp_spend_cap`

**Missing:**
- [ ] Behavioral clicktest: verify VP max display on the sheet shows highest ring + school rank (not lowest ring)

---

## 1st Dan

> Roll one extra die on precepts and any two skills of your choice.

**Status:** Fully implemented via technique_choices.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES` (choices are player-selected, not hardcoded).
- Server: `app/models.py` stores player choices in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +1 rolled die for chosen skills.
- Editor UI allows selecting skills.

**Implementation:** `app/game_data.py:2162` (`first_dan_extra_die: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_extra_die`
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_no_choice_no_bonus`

**Clicktests:**
- `test_school_abilities.py::test_isawa_ishi_1st_dan_skill_selection`

---

## 2nd Dan

> You get a free raise on all rolls for any skill of your choice.

**Status:** Fully implemented via technique_choices.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` (choice is player-selected, not hardcoded).
- Server: `app/models.py` stores player choice in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +5 flat bonus for the chosen skill.
- Editor UI allows selecting skill.

**Implementation:** `app/game_data.py:2163` (`second_dan_free_raise: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_second_dan_free_raise`

**Clicktests:**
- `test_school_abilities.py::test_isawa_ishi_2nd_dan_skill_selection`

---

## 3rd Dan

> After another character makes a roll for which void points may be spent, you may spend one void point to roll Xk1 and add the result to their total, where X is your precepts skill. You may only do this once per roll.

**Status:** Out of scope - requires cross-sheet interaction (adding roll results to another character's total).

**Questions (ANSWERED):**
- Triggered from the Isawa's side (the Isawa decides to spend their VP to help another character).
- Uses the Isawa's precepts skill rank for X.
- "Once per roll" means each roll can only receive this bonus once.

---

## 4th Dan

> Raise your current and maximum Void by 1. Raising your Void now costs 5 fewer XP. Characters opposing you in contested rolls may not spend void points. If someone is opposing both you and someone else, they may spend void points, but the bonus will only count against whoever else they're opposing.

**Status:** Partially implemented. Ring raise is fully implemented; "opponents can't spend VP in contested rolls" is out of scope (requires tracking opponent VP spending).
- Ring raise (+1 Void, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.

**Unit tests:** None specific to Isawa Ishi 4th Dan.
**Clicktests:** None.

---

## 5th Dan

> You may completely negate another character's school or profession for the remainder of one conversation or fight. Against characters with a school, you must spend void points equal to twice their school rank. Against characters with no school, you must spend void points equal to their experience divided by 50, rounded down. This is instantaneous and does not require spending an action.

**Status:** Out of scope - requires targeting another character to negate their school (cross-character debuff mechanic).
