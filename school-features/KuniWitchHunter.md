# Kuni Witch Hunter

**School ID:** `kuni_witch_hunter`
**Category:** Investigator
**School Ring:** Earth - Confirmed correct.
**School Knacks:** detect_taint, iaijutsu, presence - Detect_taint is rollable (Earth). Iaijutsu is rollable (Fire). Presence is rollable (Water).

---

## Special Ability

> You may never become Tainted. Roll an extra (X+1)k(X+1) on wound checks, where X is the Shadowlands Taint of the attacker, rounded down to the nearest whole number.

**Status:** NOT implemented. The Taint immunity is a passive narrative rule. The wound check bonus requires knowing the opponent's Taint level, which has no current tracking mechanism.

**Implementation:** `app/game_data.py:1337-1338` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement Taint immunity flag (narrative/display)
- [ ] Implement wound check bonus based on target Taint level
- [ ] UI for inputting target Taint level when making wound checks
- [ ] Unit test for wound check formula with Taint bonus

---

## 1st Dan

> Roll one extra die on damage, interrogation, and wound check rolls.

**Status:** Partially implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["damage", "interrogation", "wound_check"]`
- Interrogation and wound check extra die: applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Damage extra die: same issue as Yogo Warden - the `"damage"` entry is present but `_apply_school_technique_bonus()` is not called for damage rolls. Needs +1k0 on all damage rolls via school-specific code.

**Unit tests:** None specific to Kuni 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Implement +1k0 on all damage rolls for Kuni Witch Hunter (school-specific code in damage formula builder, same as Yogo Warden)
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

**Status:** NOT implemented. This is a reactive ability available against any opponent (not just Tainted). The reflected damage is ADDITIONAL - the Kuni takes the original damage plus half the reflected amount, which triggers an additional wound check. Against Tainted opponents, the Kuni can also attack in the current phase to add to the reflected damage.

**Missing:**
- [ ] Implement reflective damage mechanic (reflect X light wounds to attacker, take X/2 additional yourself)
- [ ] Additional wound check from the self-inflicted half damage
- [ ] Tainted-only bonus: attack in current phase adds to reflected damage
- [ ] UI for triggering reflective damage after wound check
