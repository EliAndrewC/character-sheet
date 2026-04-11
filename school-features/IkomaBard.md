# Ikoma Bard

**School ID:** `ikoma_bard`
**Category:** Artisan
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** discern_honor, oppose_knowledge, oppose_social - Discern_honor is rollable (Air). Oppose_knowledge is rollable (Air). Oppose_social is rollable (Air).

---

## Special Ability

> Force the opponent to spend their next available action die to attempt to parry; they do not get a free raise.

**Status:** NOT implemented beyond generic mechanics. This is a combat mechanic that forces the opponent to use an action on parrying.

**Implementation:** `app/game_data.py:1504-1506` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement forced-parry mechanic on opponent
- [ ] UI for triggering the forced parry
- [ ] Combat state tracking for opponent's next action die

---

## 1st Dan

> Roll an extra die on attack, bragging, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "bragging", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Ikoma 1st Dan.

**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/bragging/wound_check

---

## 2nd Dan

> Free raise on attack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "attack"`
- Applied as +5 flat bonus on attack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Ikoma at 2nd Dan gets +5 flat on attack formula
- [ ] Clicktest: attack roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Gain 2X free raises per adventure (X = bragging skill); apply to bragging, culture, heraldry, intimidation, attack, wound checks; max X per roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "bragging"`
- `applicable_to: ["bragging", "culture", "heraldry", "intimidation", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2149-2157` (third_dan dict).

**Unit tests:** None specific to Ikoma 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest for Ikoma-specific 3rd Dan applicable skills

---

## Bragging Roll Format

> Bragging rolls use a specific display format for the Ikoma Bard.

**Status:** Implemented. The display format is tested.

**Unit tests:**
- `test_display_format.py:9` - `test_bragging_ikoma_bard_format` verifies the bragging roll display format

**Clicktests:** None.

---

## 4th Dan

> +1 to a non-Void ring; that ring costs 5 fewer XP to raise; unparried attacks always roll 10 dice.

**Status:** Partially implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "Unparried attacks always roll 10 dice" is NOT implemented. This is a combat mechanic that modifies the attack formula when the attack is not parried.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement 10-dice attack mechanic for unparried attacks
- [ ] UI for indicating/tracking parry status of attacks

---

## 5th Dan

> Once per round, apply the Oppose knack or Special Ability again.

**Status:** NOT implemented. This allows reusing the Oppose knack effect or the forced-parry special ability a second time per round.

**Questions:**
- Does "apply again" mean the Ikoma gets a free use of Oppose or the Special Ability without spending an action?
- Can the Ikoma choose which one to reapply each round?

**Missing:**
- [ ] Implement per-round reuse of Oppose/Special Ability
- [ ] UI for tracking and triggering the reuse
