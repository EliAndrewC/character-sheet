# Daidoji Yojimbo

**School ID:** `daidoji_yojimbo`
**Category:** Counterattack
**School Ring:** Water - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> You may counterattack as an interrupt action by spending only 1 action die, but if you do so then your opponent gets a free raise on their wound check if you hit. You may counterattack for other characters at no penalty.

**Status:** Out of scope - "counterattack for others" requires positional tracking not supported by the app. The interrupt counterattack also requires combat-phase tracking.

**Implementation:** `app/game_data.py:1112` (definition only). No corresponding logic in `dice.py` or templates.

**Unit tests:** None.
**Clicktests:** None.

---

## 1st Dan

> Roll one extra die on attack, counterattack, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "counterattack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Daidoji 1st Dan extra die (tested generically via other schools in `test_dice.py`).
**Clicktests:**
- `test_school_abilities.py::test_daidoji_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on all counterattack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "counterattack"`
- Applied as +5 flat bonus on counterattack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the Daidoji 2nd Dan free raise on counterattack.
**Clicktests:**
- `test_school_abilities.py::test_daidoji_2nd_dan_counterattack_bonus`

---

## 3rd Dan

> When you counterattack, add X free raises to the wound check from the original attack, where X is your attack skill.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `daidoji_counterattack_raises: true` and amount. Client shows note after counterattack rolls: the original attack target gets X free raises on their wound check.

**Clicktests:**
- `test_school_abilities.py::test_daidoji_3rd_dan_counterattack_raises_note`
- `test_school_abilities.py::test_daidoji_counterattack_school_flag`

**Missing:**
- [ ] Behavioral clicktest: roll a counterattack that hits, verify the free raises note displays with correct amount

**Questions (ANSWERED):**
- X is the Daidoji's attack skill rank.
- The free raises are applied to the wound check of the person who was originally attacked (the person the Daidoji counterattacked for). The original attack still lands, and the target gets X free raises on their wound check.

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. You may choose to take the damage from a hit dealt to an adjacent character before damage has been rolled.

**Status:** Partially implemented. Ring raise is fully implemented; "take damage for adjacent character" is out of scope (positional tracking).
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

---

## 5th Dan

> After you or a character for whom you've counterattacked makes a wound check, lower the TN to hit the attacker the next time they are attacked by the amount by which the wound check exceeded the damage roll, to a minimum of 0.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `daidoji_wc_lower_tn: true`. Client shows note after passed wound checks about lowering the attacker's TN by the wound check excess.

**Clicktests:**
- `test_school_abilities.py::test_daidoji_5th_dan_wc_attacker_tn_note`

**Missing:**
- [ ] Behavioral clicktest: pass a wound check, verify the attacker TN reduction note displays with correct excess amount

---

## Test References

- No school-specific test references found in the test suite. Daidoji Yojimbo exists only in `app/game_data.py` definitions and `SCHOOL_TECHNIQUE_BONUSES`.
