# Kuni Witch Hunter

**School ID:** `kuni_witch_hunter`
**Category:** Investigator
**School Ring:** Earth - Confirmed correct.
**School Knacks:** detect_taint, iaijutsu, presence - Detect_taint is rollable (Earth). Iaijutsu is rollable (Fire). Presence is rollable (Water).

---

## Special Ability

> You may never become Tainted. Roll an extra (X+1)k(X+1) on wound checks, where X is the Shadowlands Taint of the attacker, rounded down to the nearest whole number.

**Status:** Partially implemented. Taint immunity is narrative. The Taint-based wound check bonus is not currently implemented (target Taint level tracking deferred).

**Implementation:** `app/game_data.py:1337-1338` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement wound check bonus based on target Taint level
- [ ] UI for inputting target Taint level when making wound checks
- [ ] Unit test for wound check formula with Taint bonus

---

## 1st Dan

> Roll one extra die on damage, interrogation, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["damage", "interrogation", "wound_check"]`
- Interrogation and wound check extra die: applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Damage extra die: implemented via school-specific code in `app/services/dice.py` damage section.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_kuni_witch_hunter_1st_dan_damage_extra_die` - verifies +1k0 on damage rolls
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for damage/interrogation/wound_check

---

## 2nd Dan

> You get a free raise a free on interrogation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "interrogation"`
- Applied as +5 flat bonus on interrogation rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Kuni at 2nd Dan gets +5 flat on interrogation formula
- [ ] Clicktest: interrogation roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your investigation skill, which may be applied to the following rolls: interrogation, intimidation, law, underworld, attack, and wound checks. You may also spend these free raises on damage rolls against targets with the Shadowlands Taint. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "investigation"`
- `applicable_to: ["interrogation", "intimidation", "law", "underworld", "attack", "wound_check", "damage"]`
- `formula: "2X"`, `max_per_roll: "X"`
- Note: The "damage vs Tainted" restriction is not encoded in the structured data; damage is listed unconditionally in `applicable_to`.

**Implementation:** `app/game_data.py:2075-2083` (third_dan dict).

**Unit tests:** None specific to Kuni 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None.

**Missing:**
- [ ] Implement Tainted-only restriction for damage free raises
- [ ] Clicktest for Kuni-specific 3rd Dan applicable skills

---

## 4th Dan

> Raise your current and maximum Earth by 1. Raising your Earth now costs 5 fewer XP. Roll an an extra action die in combat, which may not be used to attack targets without the Shadowlands Taint.

**Status:** Partially implemented.
- Ring raise (+1 Earth, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Extra action die (attacks only vs Tainted)" is NOT implemented. This is a combat mechanic requiring Taint tracking.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement extra action die vs Tainted mechanic
- [ ] UI for marking targets as Tainted

---

## 5th Dan

> After you take light wounds and resolve your wound check, you may choose to inflict that number of light wounds on the opponent who dealt them and take half that amount yourself. If the opponent has the Shadowlands Taint, then you may also use an attack in the current phase to add to that damage.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `kuni_reflect_damage: true` in school_abilities.
- Client: tracking section shows "Kuni 5th Dan - Reflect Damage" UI with LW input. Reflecting applies half the reflected LW as additional damage to self.
- The "Tainted-only bonus: attack in current phase adds to reflected damage" is out of scope (combat-phase tracking).

**Missing:**
- [ ] Clicktest: Kuni 5th Dan reflect damage UI and self-damage calculation
