# Kitsuki Magistrate

**School ID:** `kitsuki_magistrate`
**Category:** Investigator
**School Ring:** Water - Confirmed correct.
**School Knacks:** discern_honor, iaijutsu, presence - Discern_honor is rollable (Air). Iaijutsu is rollable (Fire). Presence is rollable (Water).

---

## Special Ability

> You use Water for interrogation rolls, and you add twice your Water to all attack rolls.

**Status:** Fully implemented.
- Water for interrogation: `app/services/dice.py:build_skill_formula()` overrides ring to Water for kitsuki_magistrate + interrogation.
- +2*Water on attacks: `app/services/dice.py:build_combat_formula()` adds 2*Water flat bonus for kitsuki_magistrate attacks.

**Implementation:** `app/game_data.py:1307-1309` (definition), `app/services/dice.py` (build_skill_formula, build_combat_formula).

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_kitsuki_magistrate_interrogation_uses_water`
- `test_dice.py::TestSchoolAbilities::test_kitsuki_magistrate_attack_water_bonus`
- `test_dice.py::TestSchoolAbilities::test_kitsuki_magistrate_parry_no_water_bonus`

**Clicktests:**
- `test_school_abilities.py::test_kitsuki_attack_water_bonus`
- `test_school_abilities.py::test_kitsuki_interrogation_uses_water`

---

## 1st Dan

> Roll one extra die on investigation, interrogation, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["investigation", "interrogation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Kitsuki 1st Dan.
**Clicktests:**
- `test_school_abilities.py::test_kitsuki_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on interrogation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "interrogation"`
- Applied as +5 flat bonus on interrogation rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_kitsuki_2nd_dan_interrogation_bonus`

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your investigation skill, which may be applied to the following rolls: interrogation, intimidation, law, underworld, attack, and wound checks. You may not spend more than X of these free raises on any single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "investigation"`
- `applicable_to: ["interrogation", "intimidation", "law", "underworld", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2062-2070` (third_dan dict).

**Unit tests:** None specific to Kitsuki 3rd Dan. The mechanism is identical to Courtier 3rd Dan which is tested in `test_dice.py`.
**Clicktests:**
- The 3rd Dan free raise UI is tested via Courtier in `test_rolls.py`.
- `test_school_abilities.py::test_kitsuki_3rd_dan_investigation_raises`

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. You automatically know the Void, parry, and phase of the next action of each character during combat, and you know the result of contested rolls made against you out of combat.

**Status:** Partially implemented. Ring raise is fully implemented; "automatically know target's Void, parry, and next action phase" is out of scope (requires opponent data not available in the app).
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.

**Unit tests:** None.
**Clicktests:** None.

---

## 5th Dan

> Your presence is so overwhelming that the Air, Fire and Water rings of chosen characters are reduced by one. You may do this to any one character, or you may do it to multiple characters so long as the sum of their experience does not exceed your experience. This does not work during the iaijutsu phase of a duel, and it does not stack with other Kitsuki Magistrates targeting the same character.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `kitsuki_reduce_rings: true`. Client shows informational note after rolls describing the ring reduction ability and its XP-based targeting limit.

**Clicktests:**
- `test_school_abilities.py::test_kitsuki_5th_dan_ring_reduction_note`
