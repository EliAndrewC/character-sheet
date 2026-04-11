# Isawa Duelist

**School ID:** `isawa_duelist`
**Category:** Duelist
**School Ring:** Water - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> Add your Water instead of Fire to your rolled damage dice.

**Status:** Fully implemented.
- `dice.py:567` sets `damage_ring_name = "Water"` when `school_id == "isawa_duelist"`.
- This causes all damage calculations for the Isawa Duelist to use Water instead of Fire.

**Implementation:** `app/services/dice.py:567` (`damage_ring_name = "Water" if school_id == "isawa_duelist" else "Fire"`).

**Unit tests:** None specific to this mechanic.
**Clicktests:** `test_sheet_js_errors.py` includes `isawa_duelist` indirectly (not in the explicit list but referenced generally).

**Missing:**
- [ ] Unit test: damage formula for Isawa Duelist uses Water ring value instead of Fire
- [ ] Clicktest: damage roll modal shows Water ring label

---

## 1st Dan

> Roll an extra die on double attack, lunge, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "lunge", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Isawa Duelist 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for double_attack/lunge/wound_check

---

## 2nd Dan

> Free raise on wound checks.

**Status:** Fully implemented.
- `second_dan_free_raise: "wound_check"`
- Applied as +5 flat bonus on wound check rolls via `_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Isawa Duelist at 2nd Dan gets +5 flat on wound check formula
- [ ] Clicktest: wound check modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Trade -5 TN to be hit next round for +3X on attack; no penalty if the attack is parried.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- What is X here? Presumably related to a skill rank.
- Is the -5 TN trade done before the attack roll? Is it a toggle?
- Does "no penalty if the attack is parried" mean the TN reduction doesn't apply if the Isawa's attack gets parried?

**Missing:**
- [ ] Implement the TN-trade-for-attack-bonus mechanic
- [ ] UI toggle or button for choosing to trade TN
- [ ] Track the TN reduction for the next round

---

## 4th Dan

> +1 Water; Water ring costs 5 fewer XP to raise; lunge once per round as an interrupt action.

**Status:** Partially implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Lunge once per round as an interrupt action" is NOT implemented. This is a combat-phase mechanic.

**Unit tests:** None specific to Isawa Duelist 4th Dan.
**Clicktests:** None.

**Missing:**
- [ ] Implement interrupt lunge mechanic (once per round)
- [ ] UI indicator for interrupt lunge availability

---

## 5th Dan

> After a successful wound check, add excess to a future wound check this combat.

**Status:** NOT implemented. This is a reactive ability that tracks wound check excess across a combat.

**Questions:**
- Does the excess accumulate across multiple wound checks?
- Is there a cap on the accumulated bonus?
- Does "this combat" mean it resets between combats?

**Missing:**
- [ ] Implement wound check excess tracking
- [ ] UI for displaying/applying accumulated wound check bonus
