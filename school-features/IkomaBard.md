# Ikoma Bard

**School ID:** `ikoma_bard`
**Category:** Artisan
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** discern_honor, oppose_knowledge, oppose_social - Discern_honor is rollable (Air). Oppose_knowledge is rollable (Air). Oppose_social is rollable (Air).

---

## Special Ability

> Once per round before making an attack roll against an opponent, you may force the opponent to spend their next available action die to attempt to parry your attack. The opponent does not get a free raise for pre-declaring the parry.

**Status:** Out of scope - requires forcing opponent to spend action die (combat-phase tracking affecting opponent).

**Implementation:** `app/game_data.py:1504-1506` (definition only).

**Unit tests:** None.
**Clicktests:** None.

---

## 1st Dan

> Roll one extra die on attack, bragging, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "bragging", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Ikoma 1st Dan.

**Clicktests:**
- `test_school_abilities.py::test_ikoma_1st_dan_formula_extra_die`

---

## 2nd Dan

> You get a free raise on attack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "attack"`
- Applied as +5 flat bonus on attack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_ikoma_2nd_dan_attack_bonus`

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your bragging skill, which may be applied to the following rolls: bragging, culture, heraldry, intimidation, attack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "bragging"`
- `applicable_to: ["bragging", "culture", "heraldry", "intimidation", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2149-2157` (third_dan dict).

**Unit tests:** None specific to Ikoma 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:**
- `test_school_abilities.py::test_ikoma_3rd_dan_bragging_raises`

---

## Bragging Roll Format

> Bragging rolls use a specific display format for the Ikoma Bard.

**Status:** Implemented. The display format is tested.

**Unit tests:**
- `test_display_format.py:9` - `test_bragging_ikoma_bard_format` verifies the bragging roll display format

**Clicktests:** None.

---

## 4th Dan

> Raise your current and maximum in any non-Void Ring by 1. Raising that Ring now costs 5 fewer XP. When making a damage roll for an unparried attack for which you are not keeping extra damage dice, you always roll 10 dice.

**Status:** Fully implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "10-dice floor on unparried damage" is implemented.
  - Server: `app/routes/pages.py` passes `ikoma_10_dice_floor: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` sets `rolled = max(rolled, 10)` in `atkComputeDamage()` when unparried and not already exceeding 10.
  - Example: Ikoma with Fire 3 and a 3k2 weapon exceeds TN by 12, gaining 2 extra rolled dice for 8k2. The 4th Dan sets rolled to max(current_rolled, 10), so 10k2. But if they exceed TN by 25+, they'd get 5+ extra rolled dice making it 11k3+ which already exceeds 10, so the technique doesn't change anything.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_ikoma_4th_dan_10_dice_floor`

---

## 5th Dan

> Once per conversation or combat round, you can apply an oppose knack or your Special ability an additional time. You may choose to use your Special Ability after an opponent has made an attack roll against you, in which case their attack is canceled and their attack roll will be used as their parry roll.

**Status:** Out of scope - requires reactive cancellation of opponent's attack roll (combat-phase tracking).
