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

**Clicktests:** None.

**Missing:**
- [x] Implement +acting_rank extra rolled dice on attack/parry/wound_check
- [x] Unit test: attack/parry/wound_check formulas include acting-based extra dice
- [ ] Clicktest: roll formulas show the acting skill bonus

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

**Clicktests:** None specific to Shosuro stipend (Merchant stipend is tested in `test_sheet_advanced.py`).

**Missing:**
- [ ] Clicktest: Shosuro Actor stipend display on character sheet

---

## 1st Dan

> Roll one extra die on attack, sincerity, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "sincerity", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Shosuro 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/sincerity/wound_check

---

## 2nd Dan

> You get a free raise on sincerity rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "sincerity"`
- Applied as +5 flat bonus on sincerity rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Shosuro at 2nd Dan gets +5 flat on sincerity formula
- [ ] Clicktest: sincerity roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your sincerity skill, which may be applied to the following rolls: acting, heraldry, sincerity, sneaking, attack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "sincerity"`
- `applicable_to: ["acting", "heraldry", "sincerity", "sneaking", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2134-2142` (third_dan dict).

**Unit tests:** None specific to Shosuro 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest for Shosuro-specific 3rd Dan applicable skills

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

**Missing:**
- [x] ~~**BUG:** Gate the stipend +5 behind 4th Dan (dan >= 4 check in `status.py`)~~ - FIXED

---

## 5th Dan

> After making any TN or contested roll, add your lowest three dice to the result. (Some dice may be counted twice.)

**Status:** NOT implemented. This is a post-roll ability that adds the lowest three dice from the roll to the total. The "(Some dice may be counted twice.)" note clarifies that dice already kept can also be among the lowest three added.

**Missing:**
- [ ] Implement lowest-three-dice addition mechanic
- [ ] UI for showing the additional dice being added
