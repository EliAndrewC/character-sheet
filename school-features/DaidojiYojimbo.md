# Daidoji Yojimbo

**School ID:** `daidoji_yojimbo`
**Category:** Counterattack
**School Ring:** Water - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> Counterattack as an interrupt action by spending only 1 action die; your opponent gets a free raise. May counterattack for others.

**Status:** NOT implemented.
- No code in `dice.py` or templates modifies counterattack behavior for Daidoji Yojimbo.
- The interrupt-for-1-die mechanic and the attacker's free raise are not tracked anywhere.
- The "may counterattack for others" mechanic (protecting adjacent allies) has no implementation.
- Daidoji Yojimbo is NOT in `SCHOOLS_WITH_TEMP_VOID` (no feint knack, no temporary void mentions).

**Implementation:** `app/game_data.py:1112` (definition only). No corresponding logic in `dice.py` or templates.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement the interrupt counterattack mechanic (1 action die cost, attacker free raise)
- [ ] Implement the "counterattack for others" mechanic
- [ ] UI indicator on the sheet showing both abilities
- [ ] Unit test: Daidoji counterattack formula reflects interrupt rules
- [ ] Clicktest: counterattack action shows the 1-die cost, attacker free raise, and ally protection option

---

## 1st Dan

> Roll an extra die on attack, counterattack, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "counterattack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Daidoji 1st Dan extra die (tested generically via other schools in `test_dice.py`).
**Clicktests:** None school-specific.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/counterattack/wound_check

---

## 2nd Dan

> Free raise on counterattack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "counterattack"`
- Applied as +5 flat bonus on counterattack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the Daidoji 2nd Dan free raise on counterattack.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Daidoji at 2nd Dan gets +5 flat on counterattack formula
- [ ] Clicktest: counterattack modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Add X free raises to wound checks from counterattack damage.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- What is X? Is it the counterattack knack rank, attack skill rank, or Dan level?
- "From counterattack damage" - does this mean the damage dealt by the counterattack translates to free raises on the next wound check the Daidoji must make?
- Is this per counterattack, or does it stack?

**Missing:**
- [ ] Implement the 3rd Dan counterattack-damage-to-wound-check-raises mechanic
- [ ] Track counterattack damage for wound check bonus calculation
- [ ] UI for displaying the accumulated free raises on wound checks
- [ ] Unit test: Daidoji 3rd Dan counterattack damage adds free raises to wound check
- [ ] Clicktest: wound check after counterattack at 3rd Dan shows bonus free raises

---

## 4th Dan

> +1 Water; Water ring costs 5 fewer XP to raise; intercept adjacent character damage before rolling.

**Status:** Partially implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Intercept adjacent character damage before rolling" is NOT implemented. This is the bodyguard mechanic where the Daidoji can take damage meant for an adjacent ally.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

**Missing:**
- [ ] Implement the 4th Dan damage interception mechanic
- [ ] UI for declaring damage interception for an adjacent character
- [ ] Unit test: Daidoji 4th Dan damage interception
- [ ] Clicktest: 4th Dan offers damage interception option

---

## 5th Dan

> Lower next attacker TN by wound check excess; minimum 0.

**Status:** NOT implemented. This modifies the attacker's TN after a successful wound check.

**Questions:**
- "Lower next attacker TN" - does this lower the TN for the next attack against the opponent who caused the wound check?
- "Wound check excess" - is this the amount by which the wound check exceeded its target number?
- "Minimum 0" - the attacker's TN cannot go below 0?

**Missing:**
- [ ] Implement the 5th Dan wound check excess to attacker TN reduction
- [ ] Track wound check excess for the TN modification
- [ ] Display the TN reduction on the next attack
- [ ] Unit test: Daidoji 5th Dan wound check excess lowers attacker TN
- [ ] Clicktest: wound check success at 5th Dan shows attacker TN reduction

---

## Test References

- No school-specific test references found in the test suite. Daidoji Yojimbo exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
