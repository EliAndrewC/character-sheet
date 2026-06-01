# Ikoma Bard

**School ID:** `ikoma_bard`
**Category:** Artisan
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** discern_honor, oppose_knowledge, oppose_social - Discern_honor is rollable (Air). Oppose_knowledge is rollable (Air). Oppose_social is rollable (Air).

---

## Special Ability

> Once per round before making an attack roll against a target, you may force the target to spend their next available action die to attempt to parry your attack.  The target does not get a free raise for pre-declaring the parry.

**Status:** Out of scope - requires forcing opponent to spend action die (combat-phase tracking affecting opponent).

**Implementation:** `app/game_data.py` (definition only).

---

## 1st Dan

> Roll one extra die on attack, bragging, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "bragging", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

---

## 2nd Dan

> You get a free raise on attack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "attack"`
- Applied as +5 flat bonus on attack rolls via `_apply_school_technique_bonus()`.

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is your bragging skill, which may be spent on bragging, culture, heraldry, intimidation, attack, and wound checks after seeing your roll.  You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "bragging"`
- `applicable_to: ["bragging", "culture", "heraldry", "intimidation", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py` (third_dan dict).

---

## Bragging Roll Format

> Bragging rolls use a specific display format for the Ikoma Bard.

**Status:** Implemented. The display format is tested.

---

## 4th Dan

> Raise your current and maximum School Ring by 1.  Raising your School Ring now costs 5 fewer XP.  When making a damage roll for an unparried attack for which you are not keeping extra damage dice, you always roll 10 dice.

**Status:** Fully implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "10-dice floor on unparried damage" is implemented.
  - Server: `app/routes/pages.py` passes `ikoma_10_dice_floor: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` sets `rolled = max(rolled, 10)` in `atkComputeDamage()` when unparried and not already exceeding 10.
  - Example: Ikoma with Fire 3 and a 3k2 weapon exceeds TN by 12, gaining 2 extra rolled dice for 8k2. The 4th Dan sets rolled to max(current_rolled, 10), so 10k2. But if they exceed TN by 25+, they'd get 5+ extra rolled dice making it 11k3+ which already exceeds 10, so the technique doesn't change anything.

---

## 5th Dan

> Once per conversation or combat round, you can apply an oppose knack or your Special ability an additional time.  You may use your Special Ability after seeing the result of any type of attack roll made against you before damage is rolled, which cancels the attack and uses the attack roll as the parry roll for your own attack.

**Status:** Out of scope - requires reactive cancellation of opponent's attack roll (combat-phase tracking).
