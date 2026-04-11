# Doji Artisan

**School ID:** `doji_artisan`
**Category:** Court
**School Ring:** "Air or Water" - Player chooses Air or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** counterattack, oppose_social, worldliness - Counterattack is rollable (varies). Oppose_social is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Spend a void point to counterattack as an interrupt action. Void point still gives +1k1. Bonus equal to attacker's roll divided by 5.

**Status:** NOT implemented beyond generic mechanics. The interrupt counterattack with VP cost and attacker-roll-based bonus would require combat-phase tracking and roll result passing.

**Implementation:** `app/game_data.py:1392-1394` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement VP-powered interrupt counterattack
- [ ] Implement bonus calculation from attacker's roll / 5
- [ ] UI for triggering interrupt counterattack

---

## 1st Dan

> Roll an extra die on counterattack, manipulation, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["counterattack", "manipulation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Doji 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for counterattack/manipulation/wound_check

---

## 2nd Dan

> Free raise on manipulation.

**Status:** Fully implemented.
- `second_dan_free_raise: "manipulation"`
- Applied as +5 flat bonus on manipulation rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Doji at 2nd Dan gets +5 flat on manipulation formula
- [ ] Clicktest: manipulation roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Gain 2X free raises per adventure (X = culture skill); apply to bragging, culture, heraldry, manipulation, counterattack, wound checks; max X per roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "culture"`
- `applicable_to: ["bragging", "culture", "heraldry", "manipulation", "counterattack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2103-2111` (third_dan dict).

**Unit tests:** None specific to Doji 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest for Doji-specific 3rd Dan applicable skills

---

## 4th Dan

> +1 Air or Water; that ring costs 5 fewer XP to raise; bonus equal to current phase when attacking untouched targets.

**Status:** Partially implemented.
- Ring raise (+1 to the chosen school ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "Air or Water", the 4th Dan ring raise applies to whichever ring was chosen.
- "Bonus equal to current phase when attacking untouched targets" is NOT implemented. This is a combat-phase mechanic.

**Unit tests:**
- `test_remaining_features.py:25` - tests SCHOOL_RING_OPTIONS for Doji (Air or Water)

**Clicktests:**
- `test_school_rings.py:35` - tests school ring selection for Doji Artisan

**Missing:**
- [ ] Implement phase-based attack bonus vs untouched targets
- [ ] UI for indicating untouched targets

---

## 5th Dan

> On TN/contested rolls, gain (X-10)/5 bonus where X is the opponent's result.

**Status:** NOT implemented. This is a reactive ability that benefits from the opponent rolling high.

**Questions:**
- Is the bonus applied after the roll? Does the Doji see the opponent's result first?
- Can the bonus be negative (if X < 10)?

**Missing:**
- [ ] Implement opponent-result-based bonus mechanic
- [ ] UI for inputting or receiving opponent roll results
