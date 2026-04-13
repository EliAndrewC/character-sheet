# Shosuro Actor

**School ID:** `shosuro_actor`
**Category:** Court
**School Ring:** Air - Confirmed correct.
**School Knacks:** athletics, discern_honor, pontificate - Athletics is rollable (varies by ring). Discern_honor is rollable (Air). Pontificate is rollable (Water).

---

## Special Ability

> Roll extra dice equal to your acting on attack, parry, and wound check rolls.

**Status:** Fully implemented.
- Attack/parry: `app/services/dice.py:build_combat_formula()` adds acting skill rank as extra rolled dice.
- Wound check: `app/services/dice.py:build_wound_check_formula()` adds acting skill rank as extra rolled dice.

**Implementation:** `app/game_data.py:1474-1476` (definition), `app/services/dice.py` (build_combat_formula, build_wound_check_formula).

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_shosuro_actor_attack_acting_bonus`
- `test_dice.py::TestSchoolAbilities::test_shosuro_actor_parry_acting_bonus`
- `test_dice.py::TestSchoolAbilities::test_shosuro_actor_wound_check_acting_bonus`
- `test_dice.py::TestSchoolAbilities::test_shosuro_actor_no_acting_skill_no_bonus`

**Clicktests:**
- `test_school_abilities.py::test_shosuro_acting_skill_bonus`

**Missing:**
- [ ] Behavioral clicktest: create char with acting skill, roll attack, verify extra rolled dice from acting appear in dice count

---

## Stipend Bonus

> Rank considered 5.0 higher for stipend (4th Dan technique mentions this).

**Status:** BUG FIXED. Now gated behind 4th Dan (dan >= 4) in `status.py`.
- `app/services/status.py:63-69` adds +5 to stipend rank when school is "merchant" or "shosuro_actor".
- The bonus is now correctly gated behind 4th Dan (dan >= 4).

**Implementation:** `app/services/status.py:63-69`.

**Unit tests:**
- `test_effective_status.py:176` - `test_household_wealth_with_shosuro_actor` verifies interaction with Household Wealth
- `test_effective_status.py:190` - `test_shosuro_actor_stipend` verifies stipend calculation
- `test_effective_status.py::TestMerchantStipend::test_shosuro_actor_stipend_below_4th_dan` - verifies no stipend bonus below 4th Dan
- `test_effective_status.py::TestMerchantStipend::test_shosuro_actor_stipend_at_4th_dan` - verifies stipend bonus at 4th Dan

**Clicktests:**
- `test_school_abilities.py::test_shosuro_stipend_display`

---

## 1st Dan

> Roll one extra die on attack, sincerity, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "sincerity", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Shosuro 1st Dan.
**Clicktests:**
- `test_school_abilities.py::test_shosuro_1st_dan_formula_extra_die`

**Missing:**
- [ ] Behavioral clicktest: roll attack or sincerity, verify extra die from 1st Dan in dice count

---

## 2nd Dan

> You get a free raise on sincerity rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "sincerity"`
- Applied as +5 flat bonus on sincerity rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_shosuro_2nd_dan_sincerity_bonus`

**Missing:**
- [ ] Behavioral clicktest: roll sincerity, verify +5 from 2nd Dan in result breakdown

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your sincerity skill, which may be applied to the following rolls: acting, heraldry, sincerity, sneaking, attack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "sincerity"`
- `applicable_to: ["acting", "heraldry", "sincerity", "sneaking", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2134-2142` (third_dan dict).

**Unit tests:** None specific to Shosuro 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:**
- `test_school_abilities.py::test_shosuro_3rd_dan_sincerity_raises`

---

## 4th Dan

> Raise your current and maximum Air by 1. Raising your Air now costs 5 fewer XP. Your Rank is considered 5.0 higher for the purpose of calculating your stipend.

**Status:** Fully implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Stipend +5 rank is implemented in `status.py:63-69` (see Stipend Bonus section above).
- The stipend bonus is now correctly gated behind 4th Dan (dan >= 4).

**Unit tests:**
- `test_effective_status.py:190` - tests stipend with Shosuro Actor
- `test_effective_status.py::TestMerchantStipend::test_shosuro_actor_stipend_below_4th_dan` - verifies no stipend bonus below 4th Dan
- `test_effective_status.py::TestMerchantStipend::test_shosuro_actor_stipend_at_4th_dan` - verifies stipend bonus at 4th Dan

**Clicktests:** None specific.

**Questions (ANSWERED):**
- Should the stipend +5 be gated behind 4th Dan? **YES.** The stipend bonus is a 4th Dan technique and should only apply at 4th Dan+. This has been fixed.

---

## 5th Dan

> After making any TN or contested roll, add your lowest three dice to the result. (Some dice may be counted twice.)

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `shosuro_add_lowest_3: true` in school_abilities.
- Client: `app/templates/character/sheet.html` auto-adds the 3 lowest dice values to the total after any TN/contested roll (not initiative). Bonus is displayed in the roll result breakdown.

**Clicktests:**
- `test_school_abilities.py::test_shosuro_5th_dan_lowest_3_dice`

