# Daidoji Yojimbo

**School ID:** `daidoji_yojimbo`
**Category:** Counterattack
**School Ring:** Water - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> You may counterattack as an interrupt action by spending only 1 action die, but if you do so then your opponent gets a free raise on their wound check if you hit. You may counterattack for other characters at no penalty.

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

> Roll one extra die on attack, counterattack, and wound check rolls.

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

> You get a free raise on all counterattack rolls.

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

> When you counterattack, add X free raises to the wound check from the original attack, where X is your attack skill.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `daidoji_counterattack_raises: true` and amount. Client shows note after counterattack rolls: the original attack target gets X free raises on their wound check.

**Questions (ANSWERED):**
- X is the Daidoji's attack skill rank.
- The free raises are applied to the wound check of the person who was originally attacked (the person the Daidoji counterattacked for). The original attack still lands, and the target gets X free raises on their wound check.

**Missing:**
- [ ] Unit test: Daidoji 3rd Dan counterattack raises flag
- [ ] Clicktest: counterattack at 3rd Dan shows wound check raises note

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. You may choose to take the damage from a hit dealt to an adjacent character before damage has been rolled.

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

> After you or a character for whom you've counterattacked makes a wound check, lower the TN to hit the attacker the next time they are attacked by the amount by which the wound check exceeded the damage roll, to a minimum of 0.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `daidoji_wc_lower_tn: true`. Client shows note after passed wound checks about lowering the attacker's TN by the wound check excess.

**Missing:**
- [ ] Unit test: Daidoji 5th Dan wound check TN reduction flag
- [ ] Clicktest: wound check at 5th Dan shows attacker TN reduction note

---

## Test References

- No school-specific test references found in the test suite. Daidoji Yojimbo exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
