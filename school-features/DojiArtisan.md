# Doji Artisan

**School ID:** `doji_artisan`
**Category:** Court
**School Ring:** "Air or Water" - Player chooses Air or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** counterattack, oppose_social, worldliness - Counterattack is rollable (varies). Oppose_social is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> You may spend a void point to counterattack as an interrupt action at the cost of one actions die; this void point still gives your counterattack +1k1. While counterattacking, you receive a bonus equal to the attacker's roll divided by 5, rounded down.

**Status:** Out of scope - requires combat-phase tracking (interrupt counterattack with VP cost and attacker-roll-based bonus).

**Implementation:** `app/game_data.py:1392-1394` (definition only).

**Unit tests:** None.
**Clicktests:** None.

---

## 1st Dan

> Roll one extra die on counterattack, manipulation, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["counterattack", "manipulation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Doji 1st Dan.
**Clicktests:** None.

---

## 2nd Dan

> You get a free raise on manipulation.

**Status:** Fully implemented.
- `second_dan_free_raise: "manipulation"`
- Applied as +5 flat bonus on manipulation rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your culture skill, which may be applied to the following rolls: bragging, culture, heraldry, manipulation, counterattack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "culture"`
- `applicable_to: ["bragging", "culture", "heraldry", "manipulation", "counterattack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2103-2111` (third_dan dict).

**Unit tests:** None specific to Doji 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None.

---

## 4th Dan

> Raise your current and maximum Air or Water by 1. Raising that ring now costs 5 fewer XP. When attacking a target who has not attacked you this round, you receive a bonus equal to the current phase.

**Status:** Partially implemented. Ring raise is fully implemented; "bonus equal to current phase when attacking untouched targets" is out of scope (combat-phase tracking).
- Ring raise (+1 to the chosen school ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "Air or Water", the 4th Dan ring raise applies to whichever ring was chosen.

**Unit tests:**
- `test_remaining_features.py:25` - tests SCHOOL_RING_OPTIONS for Doji (Air or Water)

**Clicktests:**
- `test_school_rings.py:35` - tests school ring selection for Doji Artisan

---

## 5th Dan

> When making any TN or contested roll, you receive a bonus equal to (X-10) / 5 where X is the TN or result of your opponent's contested roll.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `doji_opponent_bonus: true` in school_abilities.
- Client: shows opponent result input after any TN/contested roll. Computes `floor((opponent - 10) / 5)` and displays the adjusted total.

