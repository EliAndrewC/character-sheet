# Brotherhood of Shinsei Monk

**School ID:** `brotherhood_of_shinsei_monk`
**Category:** Monk
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** conviction, otherworldliness, worldliness - Conviction is rollable (Water). Otherworldliness and worldliness are non-rollable (passive knacks, ring=None).

---

## Special Ability

> Roll and keep one extra die for damage rolls from unarmed attacks.

**Status:** Fully implemented.
- `dice.py:581-584` adds +1 rolled and +1 kept to damage when `school_id == "brotherhood_of_shinsei_monk"` and `dan >= 1`.
- Damage bonus sources include "+1k1 from 1st Dan (unarmed)".

**Implementation:** `app/services/dice.py:581-584` (damage_extra_rolled/kept), bonus labeled "+1k1 from 1st Dan (unarmed)".

**Unit tests:**
- `test_dice.py:481` - tests damage formula for Brotherhood
- `test_dice.py:528` - tests wound check formula
- `test_dice.py:541` - tests non-rollable knacks (conviction, otherworldliness, worldliness)

**Clicktests:** `test_sheet_js_errors.py:18` includes `brotherhood_of_shinsei_monk` in the sheet JS error check list.

**Missing:**
- [ ] Clicktest: damage roll modal shows the +1k1 unarmed bonus

---

## 1st Dan

> Roll an extra die on attack, damage, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "damage", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:**
- `test_dice.py:528` - verifies wound check formula for Brotherhood

**Clicktests:** None specific to 1st Dan extra die.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/damage/wound_check

---

## 2nd Dan

> Free raise on all attack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "attack"`
- Applied as +5 flat bonus on attack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the 2nd Dan free raise on attack.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Brotherhood at 2nd Dan gets +5 flat on attack formula
- [ ] Clicktest: attack roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Gain 2X free raises per adventure (X = precepts skill); apply to history, law, precepts, wound checks, attack; can lower action dice by 5.

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

**Missing:**
- [ ] Implement "lower action dice by 5" option when spending 3rd Dan raises
- [ ] Clicktest for Brotherhood-specific 3rd Dan applicable skills

---

## 4th Dan

> +1 to a non-Void ring; that ring costs 5 fewer XP to raise; failed parries don't lower damage dice.

**Status:** Partially implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "Failed parries don't lower damage dice" is NOT implemented. This is a combat mechanic.

**Unit tests:**
- `test_remaining_features.py:20` - tests SCHOOL_RING_OPTIONS for Brotherhood (any non-Void)

**Clicktests:**
- `test_school_rings.py:26,43,67` - tests school ring selection for Brotherhood

**Missing:**
- [ ] Implement "failed parries don't lower damage dice" mechanic
- [ ] Unit test for 4th Dan parry interaction

---

## 5th Dan

> After being attacked but before damage, spend an action die to counter-attack; negates the original attack if successful.

**Status:** NOT implemented. This is a reactive combat ability.

**Questions:**
- Does the counter-attack use the normal attack formula?
- If successful, does the counter-attack also deal damage to the original attacker?
- Is this similar to the Hida Bushi special ability but with different conditions?

**Missing:**
- [ ] Implement reactive counter-attack mechanic
- [ ] UI for spending action die to counter-attack after being attacked
