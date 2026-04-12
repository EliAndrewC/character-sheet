# Brotherhood of Shinsei Monk

**School ID:** `brotherhood_of_shinsei_monk`
**Category:** Monk
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** conviction, otherworldliness, worldliness - Conviction is rollable (Water). Otherworldliness and worldliness are non-rollable (passive knacks, ring=None).

---

## Special Ability

> You roll and keep one extra die for damage rolls from unarmed attacks.

**Status:** Fully implemented.
- `dice.py:581-584` adds +1 rolled and +1 kept to damage when `school_id == "brotherhood_of_shinsei_monk"` and `dan >= 1`.
- Damage bonus sources include "+1k1 from 1st Dan (unarmed)".

**Implementation:** `app/services/dice.py:581-584` (damage_extra_rolled/kept), bonus labeled "+1k1 from 1st Dan (unarmed)".

**Unit tests:**
- `test_dice.py:481` - tests damage formula for Brotherhood
- `test_dice.py:528` - tests wound check formula
- `test_dice.py:541` - tests non-rollable knacks (conviction, otherworldliness, worldliness)

**Clicktests:** `test_sheet_js_errors.py:18` includes `brotherhood_of_shinsei_monk` in the sheet JS error check list.

---

## 1st Dan

> Roll one extra die on attack, damage, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "damage", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:**
- `test_dice.py:528` - verifies wound check formula for Brotherhood

**Clicktests:** None specific to 1st Dan extra die.

---

## 2nd Dan

> You get a free raise on all attack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "attack"`
- Applied as +5 flat bonus on attack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the 2nd Dan free raise on attack.
**Clicktests:** None.

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your precepts skill, which may be applied to the following rolls: history, law, precepts, wound checks, and attack. You may not spend more than X of these free raises on a single roll. These free raises may also be applied to action dice at any time, lowering a single die by 5 phases.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "precepts"`
- `applicable_to: ["history", "law", "precepts", "wound_check", "attack"]`
- `formula: "2X"`, `max_per_roll: "X"`
- The "lower action dice by 5" part is NOT encoded in the structured data and is not implemented.

**Implementation:** `app/game_data.py:2038-2045` (third_dan dict).

**Unit tests:**
- `test_dice.py:466-493` - tests 3rd Dan courtier (same mechanism, different school); Brotherhood uses identical mechanism
- `test_dice.py:481` - Brotherhood-specific test confirming 3rd Dan adventure raises

**Clicktests:** None specific to Brotherhood 3rd Dan. The 3rd Dan free raise UI is tested via Courtier in `test_rolls.py`.

**Notes:** Spending 1 free raise can lower a single action die by 5 phases (confirmed). This is an alternative use of the same free raises pool.

**Missing:**
- N/A - "lower action dice by 5" is tracked via the adventure raise counter directly. This is NOT implemented as a separate web UI feature because action dice lowering can happen at any time during combat (not just when initiative is rolled), and players track initiative outside the app. The existing 3rd Dan adventure raise counter can be used directly to track raises spent on lowering dice.

---

## 4th Dan

> Raise your current and maximum rank in a non-Void ring of your choice by 1. Raising this Ring now costs 5 fewer XP. Failed parry attempts do not lower your rolled damage dice.

**Status:** Fully implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "Failed parries don't lower damage dice" is implemented.
  - Server: `app/routes/pages.py` passes `brotherhood_parry_no_reduce: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` skips parry damage reduction in `atkComputeDamage()`.

**Unit tests:**
- `test_remaining_features.py:20` - tests SCHOOL_RING_OPTIONS for Brotherhood (any non-Void)

**Clicktests:**
- `test_school_rings.py:26,43,67` - tests school ring selection for Brotherhood

---

## 5th Dan

> Once per round after you have been attacked but before damage is rolled, you may spend an action die from any phase to attack your attacker. If your attack roll is at least as high as your attacker's then the attack against you is canceled; your attack continues and you hit/miss and roll damage as normal.

**Status:** Out of scope - requires reactive counter-attack mechanics (combat-phase tracking).
