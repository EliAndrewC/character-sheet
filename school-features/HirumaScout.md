# Hiruma Scout

**School ID:** `hiruma_scout`
**Category:** Investigator
**School Ring:** Air - Confirmed correct.
**School Knacks:** double_attack, feint, iaijutsu - All present and rollable. Feint knack means school is in `SCHOOLS_WITH_TEMP_VOID`.

---

## Special Ability

> Two allies fighting on your left and right have their TN to be hit raised by 5.

**Status:** NOT implemented beyond generic mechanics. This is a passive aura effect that requires positional tracking in combat.

**Implementation:** `app/game_data.py:1279-1281` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement ally TN +5 aura (positional combat mechanic)
- [ ] UI for designating adjacent allies

---

## 1st Dan

> Roll an extra die on initiative, parry, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["initiative", "parry", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()`, `build_wound_check_formula()`, and `build_initiative_formula()`.

**Unit tests:** None specific to Hiruma 1st Dan initiative logic.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Hiruma initiative formula shows extra die from 1st Dan
- [ ] Clicktest verifying the extra die appears in the roll formula display for initiative/parry/wound_check

---

## 2nd Dan

> Free raise on parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Hiruma at 2nd Dan gets +5 flat on parry formula
- [ ] Clicktest: parry roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> After a parry, add 2X to your next attack against the attacker or adjacent targets.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- What is X here? Presumably a skill rank (investigation? parry-related?).
- Is the bonus a flat +2X or 2X free raises?
- Does "adjacent targets" mean the attacker's neighbors?

**Missing:**
- [ ] Implement post-parry attack bonus mechanic
- [ ] Track bonus state between parry and next attack
- [ ] UI for applying the bonus

---

## 4th Dan

> +1 Air; Air ring costs 5 fewer XP to raise; lower action dice by 2 (minimum 1) after rolling initiative.

**Status:** Partially implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Action dice -2 is IMPLEMENTED in `dice.py:503` (`hiruma_4th_dan = school_id == "hiruma_scout" and dan >= 4`) and rendered on `sheet.html`.

**Implementation:** `app/services/dice.py:503` (`hiruma_4th_dan`), `app/templates/character/sheet.html` (initiative display).

**Unit tests:** None specific to Hiruma 4th Dan action dice.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: initiative formula for Hiruma 4th Dan includes `hiruma_4th_dan: True`
- [ ] Clicktest: initiative display shows action dice -2 information

---

## 5th Dan

> After a parry, the attacker deals 10 fewer light wounds on their next 2 damage rolls.

**Status:** NOT implemented. This is a reactive ability that modifies the attacker's future damage.

**Questions:**
- Does this stack if multiple parries are successful?
- Is the 10 fewer light wounds per damage roll or split across 2 rolls?

**Missing:**
- [ ] Implement post-parry damage reduction on attacker
- [ ] Track the 2-roll duration of the debuff
- [ ] UI for displaying active damage reduction effects
