# Courtier

**School ID:** `courtier`
**Category:** Court
**School Ring:** Air - Confirmed correct.
**School Knacks:** discern_honor, oppose_social, worldliness - Discern_honor is rollable (Air). Oppose_social is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Add your Air to all attack and damage rolls.

**Status:** Fully implemented.
- `dice.py:575-578` adds Air ring value as flat bonus to damage rolls when `school_id == "courtier"`.
- `dice.py:603-609` adds Air ring value as flat bonus to attack rolls when `school_id == "courtier"`.
- Both include labeled bonus sources (e.g., "+3 from Courtier (Air)").

**Implementation:** `app/services/dice.py:575-578` (damage flat bonus), `app/services/dice.py:603-609` (attack flat bonus).

**Unit tests:**
- `test_dice.py:466` - tests Courtier 3rd Dan (which implicitly verifies the school is set up correctly)
- `test_dice.py:493` - additional Courtier dice test

**Clicktests:**
- `test_sheet_js_errors.py:17` includes `courtier` in the sheet JS error check list.
- `test_school_selection.py:58` - tests selecting Courtier school.
- `test_school_rings.py:58` - tests Courtier school ring (fixed Air).

---

## 1st Dan

> Roll one extra die on tact, manipulation, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["tact", "manipulation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:**
- `test_roll_display.py:307` - `test_courtier_extra_die_on_tact` verifies extra die on tact formula

**Clicktests:** None specific to 1st Dan formula display.

---

## 2nd Dan

> You get a free raise on manipulation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "manipulation"`
- Applied as +5 flat bonus on manipulation rolls via `_apply_school_technique_bonus()`.

**Unit tests:**
- `test_roll_display.py:335` - `test_courtier_free_raise_on_manipulation` verifies +5 flat on manipulation

**Clicktests:** None.

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your tact skill, which may be applied to the following rolls: heraldry, manipulation, sincerity, tact, attack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "tact"`
- `applicable_to: ["heraldry", "manipulation", "sincerity", "tact", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2090-2098` (third_dan dict).

**Unit tests:**
- `test_dice.py:466-493` - tests Courtier 3rd Dan adventure raises
- `test_roll_display.py:363` - `test_courtier_third_dan` verifies 3rd Dan display

**Clicktests:**
- `test_rolls.py:309-377` - EXTENSIVE 3rd Dan free raise e2e tests:
  - `test_spend_raise_button_visible_for_applicable_skill` (line 309)
  - `test_spend_raise_adds_5_to_total` (line 319)
  - `test_undo_raise_reverses_spend` (line 330)
  - `test_spend_disabled_at_per_roll_max` (line 343)
  - `test_undo_disabled_when_none_spent` (line 355)
  - `test_no_spend_button_for_non_applicable_skill` (line 363)

**Missing:** None - 3rd Dan is fully tested.

---

## 4th Dan

> Raise your current and maximum Air by 1. Raising your Air now costs 5 fewer XP. Once per target per conversation or fight, you get a temporary void point after a successful attack or manipulation roll.

**Status:** Fully implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Temporary Void Points are tracked (school has `SCHOOLS_WITH_TEMP_VOID` via the technique text mentioning "temporary void").
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Server: `app/routes/pages.py` passes `courtier_temp_vp_on_hit: true` in school_abilities.
- Client: shows "Gain 1 temp VP (once per target)" button on attack HIT result and after manipulation skill rolls.

**Implementation:** Temp VP counter in `app/templates/character/sheet.html`, `app/routes/pages.py` (courtier_temp_vp_on_hit flag).

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific.

---

## 5th Dan

> Add your Air to all TN and contested rolls. This stacks with your Special Ability for attack rolls.

**Status:** Fully implemented.
- Skills: `app/services/dice.py:build_skill_formula()` adds +Air flat when courtier and dan >= 5.
- Knacks: `app/services/dice.py:build_knack_formula()` adds +Air flat when courtier and dan >= 5.
- Combat: `app/services/dice.py:build_combat_formula()` adds +Air flat when courtier and dan >= 5.
- Stacks with the Special Ability +Air on attacks (applied via _annotate_attack_type).

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_courtier_5th_dan_skill_air_bonus`
- `test_dice.py::TestSchoolAbilities::test_courtier_5th_dan_combat_air_bonus`
- `test_dice.py::TestSchoolAbilities::test_courtier_5th_dan_knack_air_bonus`
- `test_dice.py::TestSchoolAbilities::test_courtier_5th_dan_attack_stacks_with_special`
- `test_dice.py::TestSchoolAbilities::test_courtier_below_5th_dan_no_extra_air`

**Clicktests:** None.

