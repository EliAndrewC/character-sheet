# Shiba Bushi

**School ID:** `shiba_bushi`
**Category:** Counterattack
**School Ring:** Air - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> Parry as an interrupt action by spending your lowest 1 action die. Parry attacks directed at other characters.

**Status:** NOT implemented beyond generic mechanics. The interrupt parry and parry-for-others logic would require combat-phase tracking.

**Implementation:** `app/game_data.py:1139-1142` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement interrupt parry mechanic (spend lowest action die)
- [ ] Implement parry-for-others mechanic
- [ ] Unit tests for special ability
- [ ] Clicktest for special ability UI

---

## 1st Dan

> Roll an extra die on double attack, parry, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "parry", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Shiba 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for double_attack/parry/wound_check

---

## 2nd Dan

> Free raise on parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Shiba at 2nd Dan gets +5 flat on parry formula
- [ ] Clicktest: parry roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Parries deal (2X)k1 damage; no extra damage dice from ring or TN excess.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- What is X here? Presumably counterattack knack rank or parry-related skill rank?
- How does this interact with the damage UI? Is a separate damage roll triggered after a successful parry?
- Does "no extra damage dice from ring or TN excess" mean the damage is strictly (2X)k1 with no modifiers?

**Missing:**
- [ ] Implement parry-deals-damage mechanic
- [ ] Determine what X represents and document
- [ ] Display parry damage in the combat UI

---

## 4th Dan

> +1 Air; Air ring costs 5 fewer XP to raise; extra 3k1 on wound checks.

**Status:** Partially implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Extra 3k1 on wound checks" is NOT implemented. This is a unique bonus beyond the standard 4th Dan ring mechanics.

**Unit tests:** None specific to Shiba 4th Dan wound check bonus.
**Clicktests:** None.

**Missing:**
- [ ] Implement +3k1 on wound checks at 4th Dan
- [ ] Unit test for wound check formula showing +3 rolled +1 kept at 4th Dan
- [ ] Clicktest verifying wound check modal displays the 3k1 bonus

---

## 5th Dan

> After a successful parry, lower next attacker TN by parry excess; can go negative.

**Status:** NOT implemented. This is a reactive ability triggered after a successful parry that affects the next attack against that target.

**Questions:**
- Does "can go negative" mean the attacker's TN can drop below 0, effectively giving the Shiba's next attack a bonus?
- How long does the TN reduction last? Just the next attack?

**Missing:**
- [ ] Implement TN reduction after successful parry
- [ ] UI for displaying/tracking the TN reduction
