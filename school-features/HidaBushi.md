# Hida Bushi

**School ID:** `hida_bushi`
**Category:** Bushi
**School Ring:** Water - Confirmed correct.
**School Knacks:** counterattack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> You may counterattack as an interrupt action by spending only 1 action die, but if you do so then the attacker gets a free raise on their attack roll.

**Status:** NOT implemented.
- No code in `dice.py` or templates modifies counterattack behavior for Hida Bushi.
- The interrupt-for-1-die mechanic and the attacker's free raise are not tracked anywhere.
- Hida Bushi is NOT in `SCHOOLS_WITH_TEMP_VOID` (no feint knack, no temporary void mentions).

**Implementation:** `app/game_data.py:953` (definition only). No corresponding logic in `dice.py` or templates.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement the interrupt counterattack mechanic (1 action die cost, attacker free raise)
- [ ] UI indicator on the sheet showing this ability is available
- [ ] Unit test: Hida Bushi counterattack formula reflects interrupt rules
- [ ] Clicktest: counterattack action shows the 1-die cost and attacker free raise

---

## 1st Dan

> Roll one extra die on attack, counterattack, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "counterattack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

**Unit tests:** None specific to Hida 1st Dan extra die (tested generically via other schools in `test_dice.py`).
**Clicktests:** None school-specific.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/counterattack/wound_check

---

## 2nd Dan

> You get a free raise on all counterattack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "counterattack"`
- Applied as +5 flat bonus on counterattack rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None directly testing the Hida 2nd Dan free raise on counterattack.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Hida at 2nd Dan gets +5 flat on counterattack formula
- [ ] Clicktest: counterattack modal shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> You may re-roll 2X dice on each counterattack roll or X dice on any other attack roll, where X is your attack skill. When impaired, your number of extra dice on these rolls is divided in half (round up), but you reroll 10s on these rolls despite being impaired.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions (ANSWERED):**
- X is the attack skill rank (as with all bushi 3rd Dan techniques).
- "Re-roll dice" means rerolling that many dice and taking the better result.
- "When impaired, divided in half (round up), but reroll 10s despite being impaired" - the impaired state halves the reroll count but restores 10-rerolling on these specific rolls.

**Missing:**
- [ ] Implement the 3rd Dan reroll mechanic for counterattacks and attacks
- [ ] Handle the impaired variant (half rerolls but reroll 10s)
- [ ] UI for selecting which dice to reroll or auto-rerolling lowest
- [ ] Unit test: Hida 3rd Dan reroll mechanics
- [ ] Clicktest: counterattack/attack at 3rd Dan shows reroll option

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. Instead of making a wound check, you may choose to take 2 serious wounds to reduce your light wounds to 0. You may not do this during the iaijutsu phase of a duel.

**Status:** Partially implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Trade 2 serious wounds to reset light wounds to 0" is implemented:
  - Server: `app/routes/pages.py` passes `hida_trade_sw: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` shows a "Trade 2 SW to reset LW to 0" button in tracking section.

**Unit tests:**
- `test_remaining_features.py::TestFourthDanAutoRaise` - covers the ring raise mechanics (generic).
- `test_xp.py` - covers 4th Dan XP discount.

**Clicktests:**
- `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring` (generic).
- `test_editor_controls.py::test_fourth_dan_school_ring_max_7` (generic).

**Missing:**
- [ ] Validate the character has >= 2 serious wounds before allowing the trade
- [ ] Unit test: Hida 4th Dan wound trade mechanic
- [ ] Clicktest: 4th Dan button trades 2 SW for light wound reset

---

## 5th Dan

> When you counterattack successfully, note the quantity X by which the counterattack roll exceeded its TN. Add X to your wound check on the damage from the attack you counterattacked. You may choose to counterattack after seeing an opponent's damage roll, but that roll goes through even if your counterattack impairs or kills the opponent.

**Status:** NOT implemented. This has two parts: a wound check bonus from counterattack excess and a reactive counterattack trigger.

**Missing:**
- [ ] Implement counterattack excess tracking and wound check bonus
- [ ] Implement reactive counterattack after seeing damage
- [ ] Unit test: Hida 5th Dan counterattack excess added to wound check
- [ ] Clicktest: 5th Dan wound check reflects counterattack excess

---

## Test References

- `tests/e2e/test_school_selection.py:20` - Uses `hida_bushi` to test school selection loading details (verifies "Water" and "counterattack" appear).
