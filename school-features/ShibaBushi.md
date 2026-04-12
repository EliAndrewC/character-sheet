# Shiba Bushi

**School ID:** `shiba_bushi`
**Category:** Counterattack
**School Ring:** Air - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> You may parry as an interrupt action by spending your lowest 1 action die, and you may parry attacks directed at other characters with no penalty.

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

> You get a free raise on parry rolls.

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

> Your successful or unsuccessful parry rolls deal (2X)k1 damage, where X is equal to your attack skill. You don't roll extra damage dice from your Fire or from exceeding the TN.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions (ANSWERED):**
- X is the attack skill rank.
- This is a separate damage roll triggered after the parry resolves, since parries don't ordinarily do damage.
- Damage is strictly (2X)k1 with no modifiers from Fire or TN excess.

**Missing:**
- [ ] Implement parry-deals-damage mechanic
- [ ] Determine what X represents and document
- [ ] Display parry damage in the combat UI

---

## 4th Dan

> Raise your current and maximum Air by 1. Raising your Air now costs 5 fewer XP. You roll an extra 3k1 on wound checks.

**Status:** Fully implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "+3k1 on wound checks" is fully implemented via `app/services/dice.py:build_wound_check_formula()` (school_id == "shiba_bushi" and dan >= 4).

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_shiba_bushi_4th_dan_wound_check_3k1` - verifies +3k1 on wound checks at 4th Dan
- `test_dice.py::TestSchoolAbilities::test_shiba_bushi_below_4th_dan_no_3k1` - verifies no bonus below 4th Dan
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying wound check modal displays the 3k1 bonus

---

## 5th Dan

> After you successfully parry, the TN to hit the parried opponent on the next attack directed at them this combat is lowered by the amount by which your parry roll exceeded its TN. This can lower the TN to a negative number.

**Status:** NOT implemented. This is a reactive ability triggered after a successful parry that affects the next attack against that target.

**Missing:**
- [ ] Implement TN reduction after successful parry
- [ ] UI for displaying/tracking the TN reduction
