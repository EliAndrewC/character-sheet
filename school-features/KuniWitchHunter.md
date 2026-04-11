# Kuni Witch Hunter

**School ID:** `kuni_witch_hunter`
**Category:** Investigator
**School Ring:** Earth - Confirmed correct.
**School Knacks:** detect_taint, iaijutsu, presence - Detect_taint is rollable (Earth). Iaijutsu is rollable (Fire). Presence is rollable (Water).

---

## Special Ability

> Never become Tainted. Extra (X+1)k(X+1) on wound checks based on target's Shadowlands Taint level.

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

> Roll an extra die on damage, interrogation, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["damage", "interrogation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Kuni 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for damage/interrogation/wound_check

---

## 2nd Dan

> Free raise on interrogation rolls.

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

> Gain 2X free raises per adventure (X = investigation skill); apply to interrogation, intimidation, law, underworld, attack, wound checks, damage vs Tainted; max X per roll.

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

> +1 Earth; Earth ring costs 5 fewer XP to raise; extra action die (attacks only vs Tainted).

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

> After a wound check, inflict light wounds back on a Tainted attacker.

**Status:** NOT implemented. This is a reactive ability that only triggers against Tainted opponents.

**Questions:**
- How many light wounds are inflicted back? Is it based on the wound check result?
- Does this happen automatically or require spending a resource?

**Missing:**
- [ ] Implement reflective damage vs Tainted attackers
- [ ] UI for triggering reflective damage after wound check
