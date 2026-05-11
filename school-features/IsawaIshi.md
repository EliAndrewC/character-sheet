# Isawa Ishi

**School ID:** `isawa_ishi`
**Category:** Spellcaster
**School Ring:** Void - Confirmed correct.
**School Knacks:** absorb_void, kharmic_spin, otherworldliness - Absorb_void is non-rollable; per-adventure counter where each use regains 1 spent VP. Kharmic_spin is rollable (Void). Otherworldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Your maximum number of void points is equal to your highest ring plus your school rank. After a full night's rest, your Absorb Void school knack resets to full usage and you regain spent void points equal to your lowest Ring. A partial night's rest restores 1 spent void point and 1 use of Absorb Void per 90 minutes of sleep. However, you may not spend more void points on any one roll than your lowest Ring minus 1.

**Status:** Fully implemented.
- VP max (highest ring + school rank) is implemented in `game_data.py:872-873` via `void_points_max_shugenja()`. `app/routes/pages.py` uses `void_points_max_shugenja()` for Isawa Ishi VP max display.
- VP spend cap (`min(rings) - 1`) is computed in `app/routes/pages.py` for shugenja/isawa_ishi schools.
- VP regen (lowest ring per night) is implemented in `game_data.py:882-884` via `void_regen_per_night_shugenja()`.
- Absorb Void is per-day for Isawa Ishi (override in `app/routes/pages.py` adds `per_day=True` only when `character.school == "isawa_ishi"`), so the tracker renders the "Reset" button alongside the +/- buttons. Kitsune Warden's Absorb Void stays per-adventure (the default).

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

---

## 1st Dan

> Roll one extra die on precepts and any two types of rolls of your choice.

**Status:** Fully implemented.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES`. The two player-chosen rolls are stored in `technique_choices.first_dan_choices` (List[str], length up to 2). Eligible roll types match the Kitsune Warden 1st Dan picker: every skill (except precepts, which is auto-applied), every rollable school/foreign knack, plus attack/damage/initiative/parry/wound_check.
- Precepts is auto-applied server-side: `app/services/dice.py:_apply_school_technique_bonus()` adds +1 rolled die to precepts for `school == "isawa_ishi"` regardless of the player's picks (with dedup so a redundant explicit pick never doubles the bonus).
- Editor UI: `app/templates/character/edit.html` renders the `ishi-1st-dan-picker` block with two `<select>` slots when `school === 'isawa_ishi' && currentDan() >= 1`. Persistence and slot-uniqueness mirror the Kitsune Warden 1st Dan helpers.

**Implementation:** `app/game_data.py` (`first_dan_extra_die: None`), `app/services/dice.py:_apply_school_technique_bonus()` (auto-precepts + flexible picks), `app/templates/character/edit.html` (`ishi-1st-dan-picker` block + `setIshi1stDanChoice` Alpine helpers).

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_extra_die`
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_no_choice_no_bonus`
- `test_dice.py::TestSchoolAbilities::test_isawa_ishi_first_dan_auto_precepts`
- `test_dice.py::TestSchoolAbilities::test_isawa_ishi_first_dan_no_picks_still_grants_precepts`
- `test_dice.py::TestSchoolAbilities::test_isawa_ishi_first_dan_explicit_precepts_no_double`
- `test_dice.py::TestSchoolAbilities::test_isawa_ishi_first_dan_does_not_affect_other_schools`

**Clicktests:**
- `test_school_abilities.py::test_isawa_ishi_1st_dan_picker_applies_extra_die`
- `test_school_abilities.py::test_isawa_ishi_1st_dan_picks_persist_across_reload`

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
