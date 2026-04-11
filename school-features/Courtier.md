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

**Missing:**
- [ ] Clicktest: attack roll modal shows the +Air flat bonus
- [ ] Clicktest: damage roll modal shows the +Air flat bonus

---

## 1st Dan

> Roll an extra die on tact, manipulation, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["tact", "manipulation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:**
- `test_roll_display.py:307` - `test_courtier_extra_die_on_tact` verifies extra die on tact formula

**Clicktests:** None specific to 1st Dan formula display.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for tact/manipulation/wound_check

---

## 2nd Dan

> Free raise on manipulation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "manipulation"`
- Applied as +5 flat bonus on manipulation rolls via `_apply_school_technique_bonus()`.

**Unit tests:**
- `test_roll_display.py:335` - `test_courtier_free_raise_on_manipulation` verifies +5 flat on manipulation

**Clicktests:** None.

**Missing:**
- [ ] Clicktest: manipulation roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Gain 2X free raises per adventure (X = tact skill); apply to heraldry, manipulation, sincerity, tact, attack, wound checks; max X per roll.

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

> +1 Air; Air ring costs 5 fewer XP to raise; gain a temporary void point after a successful attack or manipulation per target.

**Status:** Partially implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Temporary Void Points are tracked (school has `SCHOOLS_WITH_TEMP_VOID` via the technique text mentioning "temporary void").
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- However, temp VP are NOT automatically granted after successful attacks/manipulation. This requires manual adjustment.

**Implementation:** Temp VP counter in `app/templates/character/sheet.html`.

**Unit tests:** None specific to the auto-grant mechanic.
**Clicktests:** None specific.

**Missing:**
- [ ] Automatically grant temp VP after successful attack or manipulation
- [ ] Clicktest: Courtier 4th Dan gains temp VP after successful attack

---

## 5th Dan

> Add your Air to all TN and contested rolls for attack rolls.

**Status:** NOT implemented. This adds Air as a bonus to the TN for contested attack rolls (making it harder for opponents to hit the Courtier) and to the Courtier's own contested attack rolls.

**Questions:**
- Does "TN and contested rolls for attack rolls" mean the Courtier's TN to be hit is increased by Air, AND the Courtier gets +Air on contested attack rolls?
- How does this interact with the Special Ability which already adds Air to attack rolls?

**Missing:**
- [ ] Implement +Air on TN for attack rolls
- [ ] Implement +Air on contested attack rolls
- [ ] Clarify interaction with Special Ability
